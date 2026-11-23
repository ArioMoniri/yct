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
STEPS = ("setup_w2l", "check_env", "push_inputs", "wav2lip", "fetch_frames")   # D-090: copy-back split out
INPUTS = "data/refstim/talkface_inputs.json"          # committed numbers-only record of the prepared inputs
SKIPS = "data/refstim/talkface_skips.jsonl"
RESULT = "data/refstim/talkface_result.json"
POD_INPUTS = "/work/yct/talkface_inputs"


class NoCapacity(RuntimeError):  # noqa: N818
    """The GPU type is not offered right now: exit 75 (re-run), nothing recorded."""


class BoxExit(RuntimeError):  # noqa: N818 - a box exit, not an error class
    """talkface_box exited non-zero: rc 10 = the pinned 'Face not detected' (s3fd_no_face skip), anything
    else = STOP (D-090 skips.box_exit). Raised only for the box process exit, never for ssh / timeouts."""

    def __init__(self, rc: int, log: str = ""):
        super().__init__(f"talkface_box exit {rc}: {log[-1500:]}")
        self.rc, self.log = int(rc), log


class EnvMismatch(RuntimeError):  # noqa: N818
    """The box `pip freeze` differs from the hashed lock (D-090 env.on_freeze_mismatch: stop)."""


def env_lock(cfg: dict) -> str:
    """The hashed box-env lock (D-090 env.lock; the former TALK_PIP list now lives in config), sha-checked."""
    env = cfg["controls"]["refclips_d090"]["env"]
    text = (ROOT / env["lock"]).read_text()
    if hashlib.sha256(text.encode()).hexdigest() != env["lock_sha256"]:
        raise Refused(f"{env['lock']} sha256 != refclips_d090.env.lock_sha256")
    return text


def check_env(cfg: dict, freeze_text: str, probe: dict) -> dict:
    """D-090 env gate on the box: pip freeze == the lock pins, torch 2.8.0+cu128 / CUDA 12.8 / python 3.11."""
    env = cfg["controls"]["refclips_d090"]["env"]
    ok, diff = T.freeze_matches(env_lock(cfg), freeze_text)
    want = env["torch"]
    tv = f"{want['version']}+{want['local']}"
    if probe.get("torch") != tv or str(probe.get("cuda")) != want["cuda"] or \
            not str(probe.get("python", "")).startswith(env["python"] + "."):
        diff.append(f"probe {probe} != torch {tv} cuda {want['cuda']} python {env['python']}")
    if not ok or diff:
        raise EnvMismatch("box env != the hashed lock: " + "; ".join(diff)[:1500])
    return {"freeze_sha256": hashlib.sha256(freeze_text.encode()).hexdigest(), "probe": probe}
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
    types = lg.types()
    if cfg["p4"]["gpu_type"] not in types:      # no capacity listed: re-run later (exit 75), never a KeyError
        raise NoCapacity(f"{cfg['p4']['gpu_type']} not in the Lambda instance-types listing")
    price = types[cfg["p4"]["gpu_type"]]["usd_per_hour"]
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
    except NoCapacity as exc:
        res.update(status="no_capacity", error=str(exc))
        return 75, res
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
    out, skip, stop = None, None, None
    try:
        box.start(iid, float(rec["deadline"]))
        for step in STEPS:
            o = box.step(step, inputs)
            res["steps"][step] = "ok"
            if step == "fetch_frames":
                out = o
    except BoxExit as exc:              # D-090: only the box process exit is classified
        if T.classify_box_exit(exc.rc) == "s3fd_no_face":
            skip = "s3fd_no_face"
        else:
            stop = f"talkface_box exit {exc.rc}: STOP (nothing logged)"
        res.update(box_rc=exc.rc, error=str(exc)[-2000:])
        out = None
    except EnvMismatch as exc:          # D-090 env.on_freeze_mismatch: stop
        stop = "box env != the hashed lock: STOP (nothing logged)"
        res.update(error=str(exc)[-2000:])
        out = None
    except Exception as exc:  # noqa: BLE001 - timeout / ssh / transfer: infrastructure, exit 75, never a skip
        res.update(status="box_failed", error=f"{type(exc).__name__}: {exc}"[-2000:])
        out = None
    finally:
        try:
            lg.terminate(iid, "job_done")
        finally:
            lg.reap()
        res["alive_after"] = lg._live(lg.list_ours())
    store.s3_put_text(f"runs/{a.run_id}/child_metrics.json", json.dumps(res, default=str))
    if stop is not None:
        res.update(status="stop", stop=stop)
        return 1, res
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
EXTRA_SHIP = ["infra/gpu_deadman.sh", "infra/talkface_lock.txt"]   # src/yct/tribe_run is in SHIP


def ship_list() -> list[str]:
    import gpu_p0_rerun as g

    out: list[str] = []
    for p in [*g.SHIP, *EXTRA_SHIP]:
        if p not in out:
            out.append(p)
    return out


def setup_script(cfg: dict, check: dict, b: str) -> str:
    tk = cfg["controls"]["refclips_d085"]["talkface"]
    env = cfg["controls"]["refclips_d090"]["env"]
    shas = "\n".join(f"echo '{check[k]}  {f}' >> pinned.sha256" for f, k in PINNED_FILES.items())
    return (f"cd {b}\n"
            "for i in $(seq 1 60); do sudo fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 || break; "
            "sleep 5; done\n"
            "APT='sudo DEBIAN_FRONTEND=noninteractive apt-get -qq'\n"
            "command -v ffmpeg >/dev/null || { $APT update && $APT install -y ffmpeg >/dev/null; }\n"
            "if [ ! -x \"$HOME/.uvbin/uv\" ]; then curl -LsSf https://astral.sh/uv/install.sh "
            "| env UV_INSTALL_DIR=\"$HOME/.uvbin\" UV_NO_MODIFY_PATH=1 sh >/dev/null; fi\n"
            "UV=$HOME/.uvbin/uv\n"
            f"[ -d w2lvenv ] || $UV venv -q -p {env['python']} --python-preference only-managed w2lvenv\n"
            f"$UV pip install -q --python w2lvenv/bin/python --require-hashes --no-deps "
            f"--index-url {env['index_url']} -r {b}/{env['lock']}\n"
            "$UV pip freeze --python w2lvenv/bin/python > w2l_pip_freeze.txt\n"
            "w2lvenv/bin/python -c \"import json,sys,torch;print(json.dumps({'torch': torch.__version__, "
            "'cuda': torch.version.cuda, 'python': sys.version.split()[0]}))\" > w2l_env_probe.json\n"
            f"[ -d Wav2Lip ] || git clone -q {tk['repo']} Wav2Lip\n"
            f"cd Wav2Lip && git checkout -q {tk['revision']} && test \"$(git rev-parse HEAD)\" = "
            f"\"{tk['revision']}\"\n"
            "rm -f pinned.sha256\n" + shas + "\nsha256sum -c pinned.sha256\n")


def push_cmd(cfg: dict, b: str) -> str:
    """Pod -> box: ONLY the NOGAN weights and s3fd from the private mirror root (D-090 mirror; the GAN
    archive is never fetched), plus the prepared inputs. __SSH__ is replaced by the box ssh command."""
    tk, m = cfg["controls"]["refclips_d085"]["talkface"], cfg["controls"]["refclips_d090"]["mirror"]
    root = tk["mirror_s3"]
    cp = "aws s3 cp --only-show-errors --region eu-central-1"
    return (f"mkdir -p /work/yct/talk_box/mirror && "
            f"{cp} {root}{m['weights']} /work/yct/talk_box/mirror/{m['weights']} && "
            f"{cp} {root}{m['s3fd']} /work/yct/talk_box/mirror/{m['s3fd']} && "
            f"cd /work/yct/talk_box && tar cf - mirror -C {POD_INPUTS}/.. talkface_inputs | "
            f"__SSH__ 'mkdir -p {b}/talk && tar xf - -C {b}/talk && "
            f"rm -rf {b}/talk/inputs && mv {b}/talk/talkface_inputs {b}/talk/inputs'")


def wav2lip_cmd(cfg: dict, b: str, inputs: dict) -> str:
    tk, m = cfg["controls"]["refclips_d085"]["talkface"], cfg["controls"]["refclips_d090"]["mirror"]
    return (f"cd {b}; export PYTHONPATH={b}/src\n"
            f"w2lvenv/bin/python -m yct.tribe_run.talkface_box --repo Wav2Lip "
            f"--weights talk/mirror/{m['weights']} --weights-sha {tk['weights_sha256']} "
            f"--s3fd talk/mirror/{m['s3fd']} --s3fd-sha {tk['face_detector_sha256']} "
            f"--face talk/inputs/static.png --face-sha {inputs['static_png_sha256']} "
            f"--audio talk/inputs/clip16k.wav --audio-sha {inputs['clip16k_wav_sha256']} --fps {tk['fps']} "
            f"--windows '{json.dumps(inputs['windows'])}' --out talk/frames.npz "
            "--record talk/w2l_record.json "
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
        elif name == "check_env":
            freeze = self.box.cat(f"{b}/w2l_pip_freeze.txt")
            probe = json.loads(self.box.cat(f"{b}/w2l_env_probe.json"))
            return check_env(self.cfg, freeze, probe)
        elif name == "push_inputs":
            g.pod(push_cmd(self.cfg, b).replace("__SSH__", self.box.ssh), 3600)
        elif name == "wav2lip":
            self.box.start("w2l", wav2lip_cmd(self.cfg, b, inputs))
            rc = self.box.wait("w2l", 3600)          # TimeoutError -> infrastructure (exit 75)
            if rc != 0:
                raise BoxExit(rc, self.box.cat(f"{b}/talk/w2l.log")[-3000:])
        elif name == "fetch_frames":                  # outside the classified block: a fault here is exit 75
            local = f"{self.pod_dir}/talk"
            g.pod(f"mkdir -p {local} && {self.box.ssh} 'cat {b}/talk/frames.npz' > {local}/frames.npz && "
                  f"{self.box.ssh} 'cat {b}/talk/w2l_record.json' > {local}/w2l_record.json && "
                  f"{self.box.ssh} 'cat {b}/w2l_pip_freeze.txt' > {local}/w2l_pip_freeze.txt", 1800)
            return {"pod_dir": local, "record": json.loads(g.pod_file(f"{local}/w2l_record.json"))}


D090_KEY = "controls.refclips_d090"
LOCAL_SCRATCH = "/work/yct/refstim_auto_scratch"


def require_d090(cfg: dict) -> None:
    if not T._frozen(cfg, D090_KEY):
        raise SystemExit(f"{D090_KEY} is not frozen: --prepare / --finish refused (council re-sign first)")


def face_source(row: dict, scratch: Path) -> Path:
    """The sha-verified TALKFACE face source on the pod (matched by content sha256 only)."""
    for f in sorted(Path(scratch).rglob("*")):
        if f.is_file() and hashlib.sha256(f.read_bytes()).hexdigest() == row["source_sha256"]:
            return f
    raise SystemExit(f"no pod file with the TALKFACE face sha {row['source_sha256'][:12]}: STOP")


def prepare_main(cfg: dict, out: Path, scratch: Path) -> dict:
    """--prepare (pod CPU, after the D-090 freeze): texts from the private page (sha-checked), the
    pin-verified espeak-ng at the D-089 TALKFACE rate, the face from the frozen rank-499 row, then
    talkface.prepare_inputs; uploads the private inputs to the mirror and writes the public record."""
    import tempfile

    import cv2

    from yct.tribe_run import refclips58 as R  # noqa: N812
    from yct.tribe_run import speech_build as B  # noqa: N812
    from yct.tribe_run import speech_corpus as S  # noqa: N812
    from yct.tribe_run.espeak_engine import EspeakSynth

    require_d090(cfg)
    T.check_frozen(cfg, ROOT)
    sel = B.check_selection_record(cfg, ROOT)
    log = [json.loads(x) for x in (ROOT / "data/refstim/image_face_auto_log_v4.jsonl").read_text()
           .splitlines() if x.strip()]
    cont = json.loads((ROOT / T.CONT).read_text())
    row = T.face_row(log, cfg, cont)
    if not T.licence_adaptable(row.get("licence", ""), cfg["controls"]["refclips"]["image_licences"]):
        raise SystemExit("TALKFACE face licence does not permit adaptation: skip licence_not_adaptable")
    spec = S.effective_spec(cfg)
    with tempfile.TemporaryDirectory() as d:
        dst = Path(d) / "raw.html"
        subprocess.run(["aws", "s3", "cp", "--only-show-errors", "--region", "eu-central-1",
                        spec["private_raw_s3"], str(dst)], check=True)
        raw = dst.read_bytes()
    queue = S.resolve_texts(json.loads((ROOT / spec["corpus_file"]).read_text()), raw)
    sel_t = B.reconstruct_texts(sel, queue, spk_words=int(spec["spk_words"]),
                                burst_sentences=int(spec["burst_sentences"]))
    synth = EspeakSynth(spec)
    (clip,) = [c for c in R.plan(cfg) if c.family == "TALKFACE"]
    B.utterance_map([clip], sel_t)
    prov = R.make_speech_provider(S.build_raw_speech(cfg, sel_t, synth))
    bgr = cv2.imread(str(face_source(row, scratch)), cv2.IMREAD_COLOR)
    if bgr is None:
        raise SystemExit("TALKFACE face source decode failed: STOP")
    rec = T.prepare_inputs(cfg, clip, prov, bgr[..., ::-1], row["crop_box"], out)
    tk = cfg["controls"]["refclips_d085"]["talkface"]
    subprocess.run(["aws", "s3", "cp", "--only-show-errors", "--region", "eu-central-1", "--recursive",
                    str(out), tk["mirror_s3"] + cfg["controls"]["refclips_d090"]["mirror"]["inputs_prefix"]],
                   check=True)
    a = cfg["controls"]["refclips_artifacts"]
    pub = {**rec, "face_source_sha256": a["talkface_face_sha256"],
           "face_rank": int(cont["talkface_face_rank"]),
           "selection_sha256": a["speech_selection_sha256"], "engine_verified": synth.verified,
           "rate_wpm": S.build_rates(cfg, sel)["TALKFACE"], "code_commit": _git("rev-parse", "HEAD")}
    B.assert_no_text(pub, sel_t)
    (ROOT / INPUTS).write_text(T.public_numbers(pub) + "\n")
    return pub


def finish_main(cfg: dict, talk_dir: Path, out: Path) -> dict:
    """--finish (pod CPU, after the session): talkface.finish_local on the pulled frames, then the clip to
    the private mirror; prints the numbers-only result (never the frames or the clip)."""
    require_d090(cfg)
    res = T.finish_local(cfg, Path(POD_INPUTS), talk_dir, out)
    tk = cfg["controls"]["refclips_d085"]["talkface"]
    dst = tk["mirror_s3"] + cfg["controls"]["refclips_d090"]["mirror"]["clip_prefix"]
    for f in ("talkface_00.mp4", "talkface_00.wav", "talkface_00.tsv"):
        subprocess.run(["aws", "s3", "cp", "--only-show-errors", "--region", "eu-central-1", str(out / f),
                        dst + f], check=True)
    return res


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
    ap.add_argument("--finish", help="pod CPU: compose + encode + QC the pulled frames in this directory")
    ap.add_argument("--local-scratch", default=LOCAL_SCRATCH)
    a = ap.parse_args(argv)
    if os.environ.get("AWS_DEFAULT_REGION", "eu-central-1") != "eu-central-1":
        raise SystemExit("AWS_DEFAULT_REGION must be eu-central-1 (yct resources only)")
    cfg = load_config()
    if a.prepare:
        print(T.public_numbers(prepare_main(cfg, Path(POD_INPUTS), Path(a.local_scratch))))
        return 0
    if a.finish:
        print(T.public_numbers(finish_main(cfg, Path(a.finish), Path(a.finish) / "clip")))
        return 0
    from infra import lambda_gpu as lg

    if a.reconcile_only:
        rec = nat.reconcile(lg, cfg, time.time)
        (ROOT / nat.RECONCILE_PATH).write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
        print(json.dumps(rec))
        return 0
    require_d090(cfg)
    if not a.external_terminator_at or not a.ci_green_sha:
        raise SystemExit("--external-terminator-at and --ci-green-sha are required for a launch")
    p4 = ref.p4
    run_dir = Path(os.environ.get("YCT_RUN_DIR") or ROOT / "outputs" / "runs" / f"p4btalk_{int(time.time())}")
    run_dir.mkdir(parents=True, exist_ok=True)
    a.external_terminator_at = p4._parse_when(a.external_terminator_at)
    a.run_id = run_dir.name
    head = _git("rev-parse", "HEAD")
    pushed = bool(_git("branch", "-r", "--contains", head))
    os.environ["YCT_HB_VIA_POD"] = "1"
    rp = ROOT / nat.RECONCILE_PATH
    recon = json.loads(rp.read_text()) if rp.exists() else None
    ip = ROOT / INPUTS
    inputs = json.loads(ip.read_text()) if ip.exists() else None
    face_log = [json.loads(x) for x in (ROOT / "data/refstim/image_face_auto_log_v4.jsonl").read_text()
                .splitlines() if x.strip()]
    cont = json.loads((ROOT / T.CONT).read_text())
    rc, res = run_session(a, cfg, lg, nat.S3Store(cfg), TalkBox(cfg, a.run_id, a.max_hours), time.time, head,
                          pushed, recon, inputs, face_log, cont, lambda out: pod_finish(out, head),
                          ROOT / SKIPS, ROOT / RESULT)
    (run_dir / "child_metrics.json").write_text(T.public_numbers(res))
    keys = ("status", "error", "box_rc", "skip_on", "qc", "pre_launch")
    print(T.public_numbers({k: res.get(k) for k in keys}))
    return rc


POD_REPO = "/work/yct/repo_talk"


def pod_finish(out: dict, head: str) -> dict:
    """--finish on the pod CPU at the launch commit (the frames never leave the pod / private mirror);
    returns the numbers-only result printed by finish_main."""
    import gpu_p0_rerun as g

    d = out["pod_dir"]
    g.pod(f"cd {POD_REPO} && git fetch -q origin && git checkout -q {head} && "
          f"AWS_DEFAULT_REGION=eu-central-1 /work/yct/venv/bin/python scripts/gpu_p4b_talk.py --finish {d} "
          f"> {d}/finish.json 2> {d}/finish.log", 5400)
    res = json.loads(g.pod_file(f"{d}/finish.json"))
    return res["qc"]


if __name__ == "__main__":
    sys.exit(main())
