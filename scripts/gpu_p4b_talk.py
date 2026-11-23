#!/usr/bin/env python3
"""D-085 part 2 step 4: the TALKFACE session (yct-p4b-ref-talk) on ONE gpu_1x_a100_sxm4. NOT launched yet:
the council pre-launch check comes first (reviews/phase_p4b/talkface_ready.md).

    python scripts/gpu_p4b_talk.py --prepare        # pod CPU: inputs + data/refstim/talkface_inputs.json
    python scripts/run_with_provenance.py --run-id p4btalk_<UTC> -- python scripts/gpu_p4b_talk.py \
        --external-terminator-at <ISO> --ci-green-sha <sha> [--max-hours 1.75] [--usd-limit 8]
    python scripts/gpu_p4b_talk.py --reconcile-only              # L4 record (as T-NAT0)

Pre-launch checks (each refuses, exit 1, before any launch): every TALKFACE dependency frozen, publish false,
the frozen loader blob + check record (talkface.check_frozen); the face = frozen rank-499 pass, adaptable
licence (talkface.face_row); the committed inputs record matches the prepared inputs; --max-hours <=
p4.launcher_max_hours, --usd-limit <= 8, price x hours <= limit; the external terminator window; HEAD ==
the CI-green commit and pushed; the L4 ledger record current; no live yct-* instance; no earlier TALKFACE
result; the D-071 (k) projection (spend + main plan + this session's worst case) <= the v2 cap and the main
campaign not started; the campaign baseline and the $75 cap guard (ref_campaign.guard_launch).
Box steps: setup_w2l (pinned venv, Wav2Lip clone at bac9a81 with the README / models / inference shas of
the loader check record), push_inputs (private mirror: NOGAN + s3fd, sha-checked on the box), wav2lip
(yct.tribe_run.talkface_box). The instance is always terminated (finally; dead-man switch on the box).
Then on the pod CPU: compose + TALKFACE QC (talkface.compose / talkface.qc + the speech gate); the clip and
frames stay private (mirror_s3); only numbers and shas are committed.
Exit codes: 0 = clip built, QC pass; 75 = re-run (no capacity, or a box step before Wav2Lip failed: nothing
recorded); 1 = a human decides: refusal, a logged face skip (s3fd_no_face / wav2lip_error: the next face
needs the frozen face continuation), or a QC failure (final STOP, the TALKFACE control reported failed).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from yct.config import load_config  # noqa: E402
from yct.tribe_run import talkface as T  # noqa: E402,N812


def _nat0():
    if "gpu_p4b_nat0" in sys.modules:
        return sys.modules["gpu_p4b_nat0"]
    spec = importlib.util.spec_from_file_location("gpu_p4b_nat0", ROOT / "scripts" / "gpu_p4b_nat0.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gpu_p4b_nat0"] = mod
    spec.loader.exec_module(mod)
    return mod


nat = _nat0()
ref = nat.ref
Refused = nat.Refused
STEPS = ("setup_w2l", "push_inputs", "wav2lip")
INPUTS = "data/refstim/talkface_inputs.json"          # committed numbers-only record of the prepared inputs
SKIPS = "data/refstim/talkface_skips.jsonl"
RESULT = "data/refstim/talkface_result.json"
POD_INPUTS = "/work/yct/talkface_inputs"
# the box env (pinned; the upstream requirements.txt (torch 1.1, librosa 0.7) cannot load the TorchScript
# archive; librosa 0.9.2 still accepts the pinned audio.py positional filters.mel call)
TALK_PIP = ["torch==2.8.0", "numpy==1.26.4", "scipy==1.11.4", "librosa==0.9.2", "numba==0.59.1",
            "llvmlite==0.42.0", "resampy==0.4.3", "soundfile==0.12.1", "opencv-python-headless==4.11.0.86",
            "tqdm==4.66.5"]
PINNED_FILES = {"README.md": "readme_sha256", "models/wav2lip.py": "models_wav2lip_py_sha256",
                "inference.py": "inference_py_sha256"}


# ---------------------------------------------------------------- pre-launch checks
def check_inputs(rec: dict | None, cfg: dict) -> dict:
    if rec is None:
        raise Refused(f"no {INPUTS}: run --prepare on the pod and commit the record first")
    want = cfg["controls"]["refclips_artifacts"]["talkface_face_sha256"]
    if rec.get("face_source_sha256") != want:
        raise Refused("talkface inputs record face sha != the frozen talkface_face_sha256")
    if rec.get("selection_sha256") != cfg["controls"]["refclips_artifacts"]["speech_selection_sha256"]:
        raise Refused("talkface inputs record selection sha != the frozen speech_selection_sha256")
    for k in ("static_png_sha256", "clip16k_wav_sha256", "rendered48k_sha256", "windows"):
        if not rec.get(k):
            raise Refused(f"talkface inputs record lacks {k}")
    return rec


def check_not_done(result_path: Path) -> None:
    if Path(result_path).exists() and json.loads(Path(result_path).read_text()).get("status") == "done":
        raise Refused("a TALKFACE result is already recorded: no second session")


def check_projection(cfg: dict, lg, *, price: float, max_hours: float, now: float) -> dict:
    """D-071 (k) projection for the TALKFACE session: campaign spend so far (NAT included) + the main
    reference campaign's plan + this session's worst case <= the v2 cap; valid only while the main campaign
    has not started (as T-NAT0 D-084). Each later NAT session re-checks its own projection."""
    rc, d = cfg["controls"]["refclips"], cfg["controls"]["refclips_d084"]
    prefix, cap = rc["ledger_name_prefix"], ref.rcmp.campaign_cap(cfg)
    talk_prefix = cfg["controls"]["refclips_d085"]["talkface"]["session_prefix"]
    _lines, records = ref._ledger(lg)
    names = [str(r.get("name", "")) for r in records if r.get("event") == "launch"]
    main = [n for n in names if n.startswith(prefix) and not n.startswith(prefix + "-nat")
            and not n.startswith(talk_prefix)]
    if main:
        raise Refused(f"the main campaign has started ({main[0]}): the projection plan is stale, "
                      "STOP to the owner")
    spend = ref.rcmp.campaign_spend(records, prefix, now)
    plan, this = float(d["main_campaign_plan_usd"]), price * max_hours
    proj = spend + plan + this
    out = {"campaign_spend_usd": round(spend, 4), "main_campaign_plan_usd": plan,
           "this_session_planned_usd": this, "projection_usd": round(proj, 4), "cap_usd": cap}
    if proj > cap + 1e-9:
        raise Refused(f"projection {proj:.2f} > ${cap:g}: STOP to the owner")
    return out


def preflight(a, cfg: dict, lg, store, clock, head: str, pushed: bool, recon: dict | None,
              inputs: dict | None, face_log: list[dict], cont: dict, result_path: Path) -> dict:
    T.check_frozen(cfg, ROOT)
    face = T.face_row(face_log, cfg, cont)
    lic = cfg["controls"]["refclips"]["image_licences"]
    if not T.licence_adaptable(face.get("licence", ""), lic):
        raise Refused("TALKFACE face licence does not permit adaptation: skip licence_not_adaptable")
    check_inputs(inputs, cfg)
    check_not_done(result_path)
    price = lg.types()[cfg["p4"]["gpu_type"]]["usd_per_hour"]
    nat.check_limits(cfg, a.max_hours, a.usd_limit, price)
    nat.check_terminator(cfg, store, a.external_terminator_at, clock(), a.max_hours)
    nat.check_commit(head, a.ci_green_sha, pushed)
    nat.check_reconcile(recon, lg)
    if lg._live(lg.list_ours()):
        raise Refused("a yct-* instance is alive: one instance at a time")
    proj = check_projection(cfg, lg, price=price, max_hours=a.max_hours, now=clock())
    ref.ensure_baseline(store, lg, cfg, clock)
    guard = ref.make_pre_launch(store, lg, cfg, clock, a.ack_cap_80)(price, a.max_hours)
    return {"price": price, "face_rank": int(cont["talkface_face_rank"]),
            "pre_launch": {**guard, "projection": proj}}


# ---------------------------------------------------------------- one session
def run_session(a, cfg: dict, lg, store, box, clock, head: str, pushed: bool, recon, inputs, face_log,
                cont, finish, skips_path: Path, result_path: Path) -> tuple[int, dict]:
    res: dict = {"session": "talk", "git_sha": head, "steps": {}}
    try:
        plan = preflight(a, cfg, lg, store, clock, head, pushed, recon, inputs, face_log, cont, result_path)
    except SystemExit as exc:
        res.update(status="refused", error=str(exc))
        return 1, res
    res.update(pre_launch=plan["pre_launch"], face_rank=plan["face_rank"])
    name = cfg["controls"]["refclips_d085"]["talkface"]["session_prefix"]
    try:
        rec = lg.launch(cfg["p4"]["gpu_type"], name, a.max_hours, "yct-pod", None, name_deadline=True)
    except SystemExit as exc:
        if "has no capacity" not in str(exc):
            raise
        res.update(status="no_capacity", error=str(exc))
        return 75, res
    except urllib.error.HTTPError as exc:
        if exc.code != 400:
            raise
        res.update(status="no_capacity", error=f"HTTP 400: {exc.read().decode(errors='replace')[:300]}")
        return 75, res
    iid = res["instance_id"] = rec["id"]
    res["terminator"] = {"kind": "external_scheduled_session", "fire_at": a.external_terminator_at}
    out, skip = None, None
    try:
        box.start(iid, float(rec["deadline"]))
        for step in STEPS:
            try:
                o = box.step(step, inputs)
            except Exception as exc:  # noqa: BLE001
                if step == "wav2lip":       # a Wav2Lip failure is a pre-stated face skip (face_rule.skip_on)
                    skip = T.classify_failure(str(exc))
                raise
            res["steps"][step] = "ok"
            if step == "wav2lip":
                out = o
    except Exception as exc:  # noqa: BLE001
        res.update(status="box_failed", error=f"{type(exc).__name__}: {exc}"[-2000:])
        out = None
    finally:
        try:
            lg.terminate(iid, "job_done")
        finally:
            lg.reap()
        res["alive_after"] = lg._live(lg.list_ours())
    store.s3_put_text(f"runs/{a.run_id}/child_metrics.json", json.dumps(res, default=str))
    if skip is not None:
        face = T.face_row(face_log, cfg, cont)
        r = T.skip_record(face, int(cont["talkface_face_rank"]), skip, a.run_id)
        with open(skips_path, "a") as f:
            f.write(json.dumps(r, sort_keys=True) + "\n")
        n = sum(1 for x in Path(skips_path).read_text().splitlines() if x.strip())
        rule = cfg["controls"]["refclips_d085"]["talkface"]["face_rule"]
        res.update(status="skip", skip_on=skip, n_skips=n,
                   next="STOP to the owner" if n >= rule["max_skips"] else "face continuation (+1 target)")
        return 1, res
    if out is None or any(res["steps"].get(s) != "ok" for s in STEPS):
        return 75, res
    try:
        q = finish(out)
    except Exception as exc:  # noqa: BLE001 - fail-closed post-session error: a human decides
        res.update(status="failed", error=f"{type(exc).__name__}: {exc}"[-2000:])
        return 1, res
    res["qc"] = q
    if not q.get("pass"):
        res.update(status="stop",
                   error="TALKFACE QC failed: final STOP to the owner (control reported failed)")
        return 1, res
    res.update(status="done")
    Path(result_path).write_text(T.public_numbers({"status": "done", "qc": q, "run_id": a.run_id,
                                                   "git_sha": head}) + "\n")
    return 0, res


# ---------------------------------------------------------------- real pod/box backend
EXTRA_SHIP = ["infra/gpu_deadman.sh"]          # src/yct/tribe_run (talkface_box, wav2lip_loader) is in SHIP


def ship_list() -> list[str]:
    import gpu_p0_rerun as g

    out: list[str] = []
    for p in [*g.SHIP, *EXTRA_SHIP]:
        if p not in out:
            out.append(p)
    return out


def setup_script(cfg: dict, check: dict, b: str) -> str:
    tk = cfg["controls"]["refclips_d085"]["talkface"]
    shas = "\n".join(f"echo '{check[k]}  {f}' >> pinned.sha256" for f, k in PINNED_FILES.items())
    return (f"cd {b}\n"
            "for i in $(seq 1 60); do sudo fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 || break; "
            "sleep 5; done\n"
            "APT='sudo DEBIAN_FRONTEND=noninteractive apt-get -qq'\n"
            "command -v ffmpeg >/dev/null || { $APT update && $APT install -y ffmpeg >/dev/null; }\n"
            "if [ ! -x \"$HOME/.uvbin/uv\" ]; then curl -LsSf https://astral.sh/uv/install.sh "
            "| env UV_INSTALL_DIR=\"$HOME/.uvbin\" UV_NO_MODIFY_PATH=1 sh >/dev/null; fi\n"
            "UV=$HOME/.uvbin/uv\n"
            "[ -d w2lvenv ] || $UV venv -q -p 3.11 w2lvenv\n"
            f"$UV pip install -q --python w2lvenv/bin/python {' '.join(TALK_PIP)}\n"
            "w2lvenv/bin/python -m pip freeze > w2l_pip_freeze.txt 2>/dev/null || "
            "$UV pip freeze --python w2lvenv/bin/python > w2l_pip_freeze.txt\n"
            f"[ -d Wav2Lip ] || git clone -q {tk['repo']} Wav2Lip\n"
            f"cd Wav2Lip && git checkout -q {tk['revision']} && test \"$(git rev-parse HEAD)\" = "
            f"\"{tk['revision']}\"\n"
            "rm -f pinned.sha256\n" + shas + "\nsha256sum -c pinned.sha256\n")


def wav2lip_cmd(cfg: dict, b: str, windows: list) -> str:
    tk = cfg["controls"]["refclips_d085"]["talkface"]
    return (f"cd {b}; export PYTHONPATH={b}/src\n"
            f"w2lvenv/bin/python -m yct.tribe_run.talkface_box --repo Wav2Lip "
            f"--weights talk/mirror/{tk['weights_file']} --weights-sha {tk['weights_sha256']} "
            f"--s3fd talk/mirror/s3fd-619a316812.pth --s3fd-sha {tk['face_detector_sha256']} "
            f"--face talk/inputs/static.png --audio talk/inputs/clip16k.wav --fps {tk['fps']} "
            f"--windows '{json.dumps(windows)}' --out talk/frames.npz --record talk/w2l_record.json "
            "> talk/w2l.log 2>&1\n")


class TalkBox(nat.PodBox):
    """The T-NAT0 box pattern (ssh from the pod, dead-man switch, heartbeat); TALKFACE steps only."""

    def ship(self) -> str:
        import base64

        g, data = self.g, nat.ship_tarball(ship_list())
        b64 = base64.b64encode(data).decode()
        g.pod(f"mkdir -p {self.pod_dir} && rm -f {self.pod_dir}/code.b64", 120)
        for i in range(0, len(b64), 20000):
            g.pod(f"echo -n {b64[i:i + 20000]} >> {self.pod_dir}/code.b64", 120)
        g.pod(f"base64 -d {self.pod_dir}/code.b64 > {self.pod_dir}/code.tgz && cat {self.pod_dir}/code.tgz | "
              f"{self.box.ssh} 'mkdir -p {g.B} && tar xzf - -C {g.B}'", 300)
        return hashlib.sha256(data).hexdigest()

    def step(self, name: str, inputs: dict):
        g, b = self.g, self.g.B
        tk = self.cfg["controls"]["refclips_d085"]["talkface"]
        if name == "setup_w2l":
            check = json.loads((ROOT / tk["loader"]["check_record"]).read_text())
            self.box.start("w2lsetup", setup_script(self.cfg, check, b))
            if self.box.wait("w2lsetup", 2400) != 0:
                raise RuntimeError("w2lsetup failed:\n" + self.box.cat("~/steps/w2lsetup.log")[-2000:])
        elif name == "push_inputs":
            g.pod("mkdir -p /work/yct/talk_box/mirror && aws s3 sync --only-show-errors "
                  f"--region eu-central-1 {tk['mirror_s3']}weights/ /work/yct/talk_box/mirror/ && "
                  f"cd /work/yct/talk_box && tar cf - mirror -C {POD_INPUTS}/.. talkface_inputs | "
                  f"{self.box.ssh} 'mkdir -p {b}/talk && tar xf - -C {b}/talk && "
                  f"mv {b}/talk/talkface_inputs {b}/talk/inputs'", 3600)
        elif name == "wav2lip":
            self.box.start("w2l", wav2lip_cmd(self.cfg, b, inputs["windows"]))
            if self.box.wait("w2l", 3600) != 0:
                raise RuntimeError("wav2lip failed:\n" + self.box.cat(f"{b}/talk/w2l.log")[-2000:])
            local = f"{self.pod_dir}/talk"
            g.pod(f"mkdir -p {local} && {self.box.ssh} 'cat {b}/talk/frames.npz' > {local}/frames.npz && "
                  f"{self.box.ssh} 'cat {b}/talk/w2l_record.json' > {local}/w2l_record.json && "
                  f"{self.box.ssh} 'cat {b}/w2l_pip_freeze.txt' > {local}/w2l_pip_freeze.txt", 1800)
            return {"pod_dir": local, "record": json.loads(g.pod_file(f"{local}/w2l_record.json"))}


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--max-hours", type=float, default=1.75)
    ap.add_argument("--usd-limit", type=float, default=nat.USD_LIMIT_MAX)
    ap.add_argument("--external-terminator-at")
    ap.add_argument("--ci-green-sha")
    ap.add_argument("--ack-cap-80", action="store_true")
    ap.add_argument("--reconcile-only", action="store_true")
    ap.add_argument("--prepare", action="store_true", help="pod CPU: build the TALKFACE inputs (no GPU)")
    a = ap.parse_args(argv)
    if os.environ.get("AWS_DEFAULT_REGION", "eu-central-1") != "eu-central-1":
        raise SystemExit("AWS_DEFAULT_REGION must be eu-central-1 (yct resources only)")
    cfg = load_config()
    if a.prepare:
        raise SystemExit("--prepare: not wired yet (council pre-launch check first, talkface_ready.md §4)")
    from infra import lambda_gpu as lg

    if a.reconcile_only:
        rec = nat.reconcile(lg, cfg, time.time)
        (ROOT / nat.RECONCILE_PATH).write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
        print(json.dumps(rec))
        return 0
    raise SystemExit("launch disabled until the council pre-launch check "
                     "(reviews/phase_p4b/talkface_ready.md)")


if __name__ == "__main__":
    sys.exit(main())
