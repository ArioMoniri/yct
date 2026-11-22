"""D-084 draft (owner "Continue same list", 2026-11-22, decided after seeing the session-0 result 4/40):
NAT continuation sessions k >= 1 down the same frozen snapshot, same frozen rules. Fakes only; no GPU."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from yct.config import load_config
from yct.curate import natstim as ns
from yct.curate import refstim_auto as ra

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config()
EN, ONE = {"en": 0.99}, [[0.0, 50.0, "S0"]]
NAT_N = CFG["controls"]["refclips"]["nat_n"]
BUF = CFG["controls"]["refclips_auto"]["nat"]["cpu_buffer"]


def cpu(ids, rejects_every=0):
    out = []
    for j, i in enumerate(ids):
        out.append({"stage": "cpu", "decision": "pass", "t1_name": i, "title": f"File:{i}.webm", "url": "u",
                    "values": {"licence": "CC0", "licence_template": "Template:Cc-zero"}})
        if rejects_every and j % rejects_every == 0:
            out.append({"stage": "cpu", "decision": "reject", "t1_name": None, "title": f"File:r{i}.webm",
                        "reason": "licence", "rule": "C1"})
    return out


def gpu(ids, good):
    return {i: {"lang_probs": EN if i in good else {"en": 0.2}, "segments": ONE} for i in ids}


def s0(ids, good):
    return ns.session0_rows(ids, gpu(ids, good), lambda i: 0.9, CFG) if \
        sum(i in good for i in ids) >= NAT_N else _s0_stop(ids, good)


def _s0_stop(ids, good):
    with pytest.raises(ns.Session0Stop) as e:
        ns.session0_rows(ids, gpu(ids, good), lambda i: 0.9, CFG)
    return e.value.rows


IDS = [f"c{i:03d}" for i in range(200)]


# ---------------------------------------------------------------- config
def test_d084_config_block():
    d = CFG["controls"]["refclips_d084"]
    assert d["decision"] == "D-084" and d["amends"] == ["D-075"]
    assert d["post_hoc"] is True and d["evaluate_full_buffer"] is True
    assert d["selection"] == "first_nat_n_by_cpu_rank" and d["buffer_per_session"] == BUF
    assert 1 <= d["max_sessions"] <= 10 and d["cpu_ahead_max"] == 1


# ---------------------------------------------------------------- buffers
def test_buffer_k_is_the_kth_block_of_40_cpu_passes():
    log = cpu(IDS[:100], rejects_every=3)
    assert ns.buffer_ids(log, CFG, 0) == IDS[:40]
    assert ns.buffer_ids(log, CFG, 1) == IDS[40:80]
    assert ns.buffer_ids(log, CFG, 2) == IDS[80:100]
    assert ns.buffer_ids(log, CFG) == IDS[:40]          # session 0 default unchanged


def test_buffer_k_with_39_passes_is_incomplete():
    log = cpu(IDS[:79])
    assert ns.buffer_complete(log, CFG, 0) and not ns.buffer_complete(log, CFG, 1)
    log2 = log + [{"stage": ns.STAGE_CPU_END, "reason": "snapshot_exhausted", "n_evaluated": 79,
                   "n_pass": 79, "n_order": 79}]
    assert ns.buffer_complete(log2, CFG, 1)             # short LAST buffer only with the terminal record


# ---------------------------------------------------------------- continuation rows
def test_continuation_evaluates_the_full_buffer_no_early_stop():
    buf = IDS[40:80]
    rows = ns.session_rows(1, buf, gpu(buf, set(buf)), lambda i: 0.9, CFG)
    assert len(rows) == 40 and all(r["stage"] == ns.STAGE_SK and r["session"] == 1 for r in rows)
    assert sum(r["decision"] == "pass" for r in rows) == 40        # > nat_n: all evaluated, all logged


def test_continuation_missing_output_and_k0_refused():
    with pytest.raises(ra.StopError, match="no N1/N2"):
        ns.session_rows(1, ["a", "b"], gpu(["a"], {"a"}), lambda i: 0.9, CFG)
    with pytest.raises(ra.StopError, match="k >= 1"):
        ns.session_rows(0, ["a"], gpu(["a"], {"a"}), lambda i: 0.9, CFG)


# ---------------------------------------------------------------- selection
def _logs_by_sessions(good, bounds):
    """CPU rows for IDS[:bounds[-1]] then session rows per block [bounds[j], bounds[j+1])."""
    log = cpu(IDS[:bounds[-1]])
    first = IDS[bounds[0]:bounds[1]]
    log += s0(first, good)
    for k, (a, b) in enumerate(zip(bounds[1:-1], bounds[2:], strict=True), start=1):
        blk = IDS[a:b]
        log += ns.session_rows(k, blk, gpu(blk, good), lambda i: 0.9, CFG)
    return log


def test_selection_is_first_nat_n_by_cpu_rank_and_keeps_session0_passes():
    good = {IDS[i] for i in (3, 9, 17, 30)} | {IDS[i] for i in range(41, 120, 7)}
    log = _logs_by_sessions(good, [0, 40, 80, 120])
    sel = ns.nat_selection(log, CFG)
    want = sorted(good, key=IDS.index)[:NAT_N]
    assert sel == want and sel[:4] == [IDS[3], IDS[9], IDS[17], IDS[30]]


def test_selection_invariant_to_session_boundaries():
    good = {IDS[i] for i in range(0, 120, 6)}
    a = ns.nat_selection(_logs_by_sessions(good, [0, 40, 80, 120]), CFG)
    # same CPU rows, same decisions, different session split (session 0 always the first 40)
    b_log = cpu(IDS[:120]) + s0(IDS[:40], good)
    for k, (x, y) in enumerate([(40, 60), (60, 120)], start=1):
        blk = IDS[x:y]
        b_log += ns.session_rows(k, blk, gpu(blk, good), lambda i: 0.9, CFG)
    assert a == ns.nat_selection(b_log, CFG)
    # log order of the session rows does not matter either
    rows = [r for r in b_log if r["stage"] != "cpu"]
    assert ns.nat_selection(cpu(IDS[:120]) + rows[::-1], CFG) == a


def test_selection_refuses_duplicates_and_gaps():
    good = set(IDS[:80])
    log = cpu(IDS[:80]) + s0(IDS[:40], set())
    dup = log + ns.session_rows(1, IDS[30:70], gpu(IDS[30:70], good), lambda i: 0.9, CFG)
    with pytest.raises(ra.StopError, match="evaluated twice"):
        ns.nat_selection(dup, CFG)
    gap = log + ns.session_rows(1, IDS[41:80], gpu(IDS[41:80], good), lambda i: 0.9, CFG)
    with pytest.raises(ra.StopError, match="prefix"):
        ns.nat_selection(gap, CFG)
    alien = log + ns.session_rows(1, ["zz"], gpu(["zz"], good), lambda i: 0.9, CFG)
    with pytest.raises(ra.StopError, match="not a CPU pass"):
        ns.nat_selection(alien, CFG)


def test_nat_manifest_uses_cumulative_selection():
    good = {IDS[i] for i in (1, 2, 3, 4)} | set(IDS[40:60])
    log = _logs_by_sessions(good, [0, 40, 80])
    m = ns.nat_manifest(log, CFG)
    assert [r["t1_name"] for r in m] == sorted(good, key=IDS.index)[:NAT_N]
    short = _logs_by_sessions({IDS[1]} | set(IDS[40:50]), [0, 40, 80])
    with pytest.raises(ra.StopError, match="nat_n"):
        ns.nat_manifest(short, CFG)


# ---------------------------------------------------------------- CPU target guard
def test_cpu_target_never_more_than_one_buffer_ahead():
    log = cpu(IDS[:40]) + s0(IDS[:40], set(IDS[:4]))
    assert ns.check_cpu_target(log, CFG, 2) == 2 * BUF
    with pytest.raises(ra.StopError, match="ahead"):
        ns.check_cpu_target(log, CFG, 3)
    with pytest.raises(ra.StopError, match="ahead"):
        ns.check_cpu_target(cpu(IDS[:40]), CFG, 2)          # session 0 not yet evaluated
    assert ns.check_cpu_target(cpu(IDS[:10]), CFG, 1) == BUF


def test_cpu_target_refused_once_selection_complete_or_over_max():
    full = cpu(IDS[:40]) + s0(IDS[:40], set(IDS[:20]))
    with pytest.raises(ra.StopError, match="complete"):
        ns.check_cpu_target(full, CFG, 2)
    c = copy.deepcopy(CFG)
    c["controls"]["refclips_d084"]["max_sessions"] = 1
    log = cpu(IDS[:80]) + s0(IDS[:40], set()) + \
        ns.session_rows(1, IDS[40:80], gpu(IDS[40:80], set()), lambda i: 0.9, c)
    with pytest.raises(ra.StopError, match="max_sessions"):
        ns.check_cpu_target(log, c, 3)


def test_run_cpu_fills_to_the_n_buffer_target(tmp_path):
    order = [{"title": f"File:{i}.webm", "pageid": n, "revid": 1} for n, i in enumerate(IDS[:100])]
    logp = tmp_path / "log.jsonl"
    meta = {"templates": ["Template:Cc-zero"], "license_short": "", "duration": 120.0, "description": "",
            "categories": "", "read_revid": 1, "artist": "A", "credit": "", "commons_sha1": "s"}

    def page_meta(titles):
        return {t: {**meta, "url": f"https://upload.wikimedia.org/{t}"} for t in titles}

    def fetch(e, m):
        i = e["title"][5:-5]
        return {"trimmed_duration_s": 60.0, "source_sha1": "s", "source_sha256": "h", "sha256": "t",
                "video_id": i, "wav_sha256": "w"}

    def nd(rec, cfg):
        return None, None

    orig = ns.normalised_decide
    ns.normalised_decide = nd
    try:
        ns.run_cpu(order, CFG, logp, page_meta, fetch, set(), 1, set())
        assert len(ns.cpu_rows(ns.load_log(logp))) == 40
        ns.run_cpu(order, CFG, logp, page_meta, fetch, set(), 1, set(), n_buffers=2)
        rows = ns.cpu_rows(ns.load_log(logp))
        assert len(rows) == 80 and [r["t1_name"] for r in rows] == IDS[:80]   # resumed, in order
    finally:
        ns.normalised_decide = orig


# ---------------------------------------------------------------- driver (session k)
spec = importlib.util.spec_from_file_location("gpu_p4b_nat0", ROOT / "scripts" / "gpu_p4b_nat0.py")
nat0 = sys.modules.get("gpu_p4b_nat0")
if nat0 is None:
    nat0 = importlib.util.module_from_spec(spec)
    sys.modules["gpu_p4b_nat0"] = nat0
    spec.loader.exec_module(nat0)
p4 = nat0.ref.p4
HEAD = "c" * 40


def dcfg(frozen84=True):
    c = copy.deepcopy(load_config())
    for k in nat0.PYANNOTE_KEYS:
        c["controls"]["refclips_auto_artifacts"][k] = "a" * 64
        c["frozen"].append({"key": f"controls.refclips_auto_artifacts.{k}", "frozen_at": "x"})
    c["frozen"].append({"key": "controls.refclips_d082", "frozen_at": "x"})
    if frozen84:
        c["frozen"].append({"key": "controls.refclips_d084", "frozen_at": "x"})
    else:
        c["frozen"] = [r for r in c["frozen"] if r["key"] != "controls.refclips_d084"]
    return c


class Store:
    def __init__(self):
        self.d = {}

    def s3_get_text(self, k):
        return self.d.get(k)

    def s3_put_text(self, k, t):
        self.d[k] = t

    def s3_list(self, prefix):
        return {k: 1 for k in self.d if k.startswith(prefix)}


class Box:
    def __init__(self, good):
        self.good, self.calls, self.buffers = set(good), [], []

    def start(self, iid, deadline):
        self.calls.append("start")

    def step(self, name, buffer):
        self.calls.append(name)
        if name == "nat0":
            self.buffers.append(list(buffer))
            return {"results": gpu(buffer, self.good)}

    def n3(self, i):
        return 0.9


@pytest.fixture
def env(tmp_path):
    clock = p4.FakeClock(1_800_000_000.0)
    lg = p4.FakeLG(clock, tmp_path / "ledger.jsonl")
    log = tmp_path / "nat_auto_log.jsonl"
    rows = cpu(IDS[:80]) + s0(IDS[:40], set(IDS[:4]))
    log.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return SimpleNamespace(clock=clock, lg=lg, log=log, store=Store())


def runk(env, k, c=None, box=None, ext_off=1000):
    c = c or dcfg()
    ext = env.clock() + 1.75 * 3600 + ext_off
    a = SimpleNamespace(max_hours=1.75, usd_limit=8.0, external_terminator_at=ext,
                        ci_green_sha=HEAD, ack_cap_80=False, run_id=f"p4bnat{k}_test", session=k)
    recon = nat0.reconcile(env.lg, c, env.clock)
    cpu_state = {"alive": False, "pod_log_sha256": hashlib.sha256(env.log.read_bytes()).hexdigest()}
    return nat0.run_session0(a, c, env.lg, env.store, box or Box(set()), env.clock, env.log, HEAD, True,
                             recon=recon, cpu_state=cpu_state)


def logged(env):
    return [json.loads(x) for x in env.log.read_text().splitlines()]


def test_session1_runs_buffer1_and_logs_all_rows(env):
    box = Box(set(IDS[40:80:4]))
    rc, res = runk(env, 1, box=box)
    assert rc == 0 and res["status"] == "next_buffer", res          # 4 + 10 = 14 < 15
    assert box.buffers == [IDS[40:80]] and box.calls == ["start", *nat0.STEPS]
    r1 = [r for r in logged(env) if r.get("session") == 1]
    assert len(r1) == 40 and res["n_pass_total"] == 14
    (iid,) = env.lg.launched
    assert env.lg.api.inst[iid]["name"].startswith("yct-p4b-ref-nat1-") and env.lg.status[iid] == "terminated"


def test_session1_selected_when_cumulative_reaches_nat_n(env):
    rc, res = runk(env, 1, box=Box(set(IDS[40:60])))
    assert rc == 0 and res["status"] == "selected" and res["n_pass_total"] == 24
    assert len([r for r in logged(env) if r.get("session") == 1]) == 40      # full buffer, no early stop


@pytest.mark.parametrize("k,match", [(2, "session 1 not logged"), (0, "already logged")])
def test_session_sequence_refusals(env, k, match):
    rc, res = runk(env, k)
    assert rc == 1 and match in res["error"] and env.lg.launched == []


def test_session_k_refused_when_buffer_short(env):
    rows = [r for r in logged(env) if not (r["stage"] == "cpu" and r["t1_name"] == IDS[79])]
    env.log.write_text("".join(json.dumps(r) + "\n" for r in rows))
    rc, res = runk(env, 1)
    assert rc == 1 and "39 of 40" in res["error"] and env.lg.launched == []


def test_session_k_refused_without_d084_freeze(env):
    rc, res = runk(env, 1, c=dcfg(frozen84=False))
    assert rc == 1 and "refclips_d084" in res["error"] and env.lg.launched == []


def test_session_k_refused_when_selection_complete(env):
    assert runk(env, 1, box=Box(set(IDS[40:60])))[0] == 0
    env.log.write_text("".join(json.dumps(r) + "\n" for r in logged(env) + cpu(IDS[80:120])))
    rc, res = runk(env, 2, ext_off=1500)
    assert rc == 1 and "complete" in res["error"]


def test_session_k_refused_over_max_sessions(env):
    c = dcfg()
    c["controls"]["refclips_d084"]["max_sessions"] = 0
    rc, res = runk(env, 1, c=c)
    assert rc == 1 and "max_sessions" in res["error"]


def test_session_k_refused_on_overlap(env):
    # a buffer-1 id already evaluated (e.g. a hand-written row) -> refused, never re-evaluated
    # council D-084 (biostat): the row carries the session-0 stage so the sequencing check passes and the
    # overlap check itself is the one that refuses (it runs before the selection's gap check)
    rows = logged(env) + [{"stage": ns.STAGE_S0, "t1_name": IDS[45], "decision": "reject",
                           "rule": "N1", "reason": "not_english", "values": {}}]
    env.log.write_text("".join(json.dumps(r) + "\n" for r in rows))
    rc, res = runk(env, 1)
    assert rc == 1 and "already evaluated" in res["error"] and IDS[45] in res["error"]
    assert env.lg.launched == []


def test_finish_k_stops_at_max_sessions(env):
    # council D-084 (biostat): k = max_sessions with < nat_n cumulative passes -> exit 1, STOP to the owner
    c = dcfg()
    c["controls"]["refclips_d084"]["max_sessions"] = 1
    rc, res = runk(env, 1, c=c, box=Box({IDS[40]}))
    assert rc == 1 and res["status"] == "stop" and "STOP to the owner" in res["error"]
    assert len([r for r in logged(env) if r.get("session") == 1]) == 40      # rows logged before the STOP
    assert res["n_pass_total"] == 5


def test_finish_k_stops_when_snapshot_exhausted(env):
    # council D-084 (biostat): a short last buffer (snapshot exhausted) evaluated with < nat_n -> exit 1
    rows = [r for r in logged(env) if not (r["stage"] == "cpu" and r["t1_name"] in IDS[70:80])]
    rows.append({"stage": ns.STAGE_CPU_END, "reason": "snapshot_exhausted", "n_evaluated": 70, "n_pass": 70})
    env.log.write_text("".join(json.dumps(r) + "\n" for r in rows))
    rc, res = runk(env, 1, box=Box({IDS[40]}))
    assert rc == 1 and res["status"] == "stop" and "snapshot exhausted" in res["error"]
    assert len([r for r in logged(env) if r.get("session") == 1]) == 30


def test_snapshot_exhausted_at_buffer_boundary_refuses_without_launch(env):
    # D-084 §2.5: the CPU stage reaches the snapshot end only after buffer k-1 was full (exhaustion exactly at
    # a buffer boundary), so buffer k is empty: session k is refused and nothing is launched
    c = dcfg()
    assert runk(env, 1, c=c, box=Box(set()))[0] == 0      # buffer 1 evaluated: 4 passes, k < max_sessions
    rows = logged(env) + [{"stage": ns.STAGE_CPU_END, "reason": "snapshot_exhausted", "n_evaluated": 80,
                           "n_pass": 80}]
    env.log.write_text("".join(json.dumps(r) + "\n" for r in rows))
    rc, res = runk(env, 2, c=c, ext_off=1500)
    assert rc == 1 and "buffer 2 is empty" in res["error"] and len(env.lg.launched) == 1


# ---------------------------------------------------------------- council D-084 (watchdog): projection
def test_projection_recorded_in_pre_launch(env):
    rc, res = runk(env, 1, box=Box(set()))
    pr = res["pre_launch"]["projection"]
    plan = dcfg()["controls"]["refclips_d084"]["main_campaign_plan_usd"]
    assert pr["main_campaign_plan_usd"] == plan and abs(pr["this_session_planned_usd"] - 1.99 * 1.75) < 1e-6
    want = pr["campaign_spend_usd"] + plan + pr["talkface_plan_usd"] + pr["this_session_planned_usd"]
    assert abs(pr["projection_usd"] - want) < 1e-6
    assert pr["cap_usd"] == 75


def test_projection_includes_the_d085_talkface_session_worst_case(env):
    # council D-085 (watchdog): TALKFACE runs as its own GPU session, so its worst case joins the projection
    rc, res = runk(env, 1, box=Box(set()))
    pr = res["pre_launch"]["projection"]
    assert pr["talkface_plan_usd"] == dcfg()["controls"]["refclips_d085"]["talkface"]["session_worst_usd"]
    c = dcfg()
    c["controls"]["refclips_d084"]["main_campaign_plan_usd"] = 75 - 1.99 * 1.75 - 1.0   # fits w/o TALKFACE
    with pytest.raises(nat0.Refused, match="TALKFACE"):
        nat0.check_projection(c, env.lg, price=1.99, max_hours=1.75, now=env.clock(), k=1)


def test_talkface_session_does_not_count_as_the_main_campaign(env):
    gt = dcfg()["p4"]["gpu_type"]
    rec = env.lg.launch(gt, "yct-p4b-ref-talk", 0.1, "yct-pod", None, name_deadline=True)
    env.lg.terminate(rec["id"], "job_done")
    rc, res = runk(env, 1, box=Box(set()))
    assert "main campaign" not in str(res.get("error", ""))


def test_projection_over_cap_is_a_stop_before_launch(env):
    c = dcfg()
    c["controls"]["refclips_d084"]["main_campaign_plan_usd"] = 72.0      # 72 + 3.48 > 75
    rc, res = runk(env, 1, c=c)
    assert rc == 1 and res["status"] == "refused" and "projection" in res["error"]
    assert "STOP to the owner" in res["error"] and env.lg.launched == []


def test_projection_refused_once_main_campaign_started(env):
    # the plan figure holds only before any non-NAT yct-p4b-ref launch; afterwards a human re-plans
    gt = dcfg()["p4"]["gpu_type"]
    rec = env.lg.launch(gt, "yct-p4b-ref-s1", 0.1, "yct-pod", None, name_deadline=True)
    env.lg.terminate(rec["id"], "job_done")
    rc, res = runk(env, 1)
    assert rc == 1 and "main campaign" in res["error"] and len(env.lg.launched) == 1


def test_projection_not_applied_to_session0(env):
    c = dcfg()
    c["controls"]["refclips_d084"]["main_campaign_plan_usd"] = 72.0
    assert nat0.check_projection(c, env.lg, price=1.99, max_hours=1.75, now=env.clock(), k=0) is None


def test_session0_path_unchanged_for_k0_default(env, tmp_path):
    # a fresh log (no session rows): session 0 still works with the default k = 0
    log = tmp_path / "fresh.jsonl"
    log.write_text("".join(json.dumps(r) + "\n" for r in cpu(IDS[:40])))
    env.log = log
    rc, res = runk(env, 0, box=Box(set(IDS[:20])))
    assert rc == 0 and res["status"] == "done"


def test_cpu_runner_cli_buffers_option():
    spec2 = importlib.util.spec_from_file_location("natstim_cpu_run", ROOT / "scripts" / "natstim_cpu_run.py")
    m = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(m)
    assert m.parse(["run", "/s"]) == (Path("/s"), 1)
    assert m.parse(["run", "/s", "--buffers", "2"]) == (Path("/s"), 2)
    with pytest.raises(SystemExit):
        m.parse(["run", "/s", "--x", "2"])


def test_real_log_allows_exactly_buffer_1_now():
    log = ns.load_log(ROOT / CFG["controls"]["refclips_auto"]["logs"]["nat"])
    assert ns.sessions_logged(log) == [0] and len(ns.nat_selection(log, CFG)) == 4
    assert ns.check_cpu_target(log, CFG, 2) == 80
    with pytest.raises(ra.StopError, match="ahead"):
        ns.check_cpu_target(log, CFG, 3)
