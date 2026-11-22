"""Schema for config.yaml (QA P0 #1, FIX-C3-ENG): every section is a pydantic model with extra="forbid"
and strict types, so a mistyped key, a wrong type or a missing key fails at load time instead of being
silently replaced by a `.get()` default. `yct.config.load_config(validate=True)` (the default) uses it.

Strict mode: no str -> number coercion; an int is accepted where a float is expected.
Adding/renaming a config key therefore needs a matching change here (and tests/test_config_schema.py).
"""
from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Sha1 = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
Pos = Annotated[float, Field(gt=0)]
NonNeg = Annotated[float, Field(ge=0)]
PosInt = Annotated[int, Field(gt=0)]
Frac = Annotated[float, Field(ge=0, le=1)]


class M(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


# ---------------------------------------------------------------- core
class Tribe(M):
    tr_s: Pos
    n_vertices: Literal[20484]


class Stimulus(M):
    t1_trim_s: Pos
    t1_max_probe_s: Pos
    fps: PosInt
    min_source_fps: PosInt
    min_short_side_px: PosInt
    center_crop_px: PosInt

    @model_validator(mode="after")
    def _probe(self):
        if self.t1_max_probe_s < self.t1_trim_s:
            raise ValueError("t1_max_probe_s must be >= t1_trim_s")
        if self.center_crop_px > self.min_short_side_px:
            raise ValueError("center_crop_px must be <= min_short_side_px")
        return self


class Window(M):
    default_start_tr: PosInt
    default_len_tr: PosInt
    min_tail_s: NonNeg
    latency_l_tr: Annotated[int, Field(ge=0)]    # D-063 B1
    start_tr: PosInt
    end_tr: PosInt

    @model_validator(mode="after")
    def _w_rule(self):
        if self.start_tr != max(5, 4 + self.latency_l_tr + 1):
            raise ValueError("window.start_tr must equal max(5, 4 + latency_l_tr + 1) (v2.md W rule)")
        if self.end_tr - self.start_tr != self.default_len_tr:
            raise ValueError("window.end_tr - start_tr must equal default_len_tr")
        return self


class Era(M):
    first_batch: Annotated[str, Field(pattern=r"^[SWF]\d{4}$")] | None = None
    last_batch: Annotated[str, Field(pattern=r"^[SWF]\d{4}$")] | None = None


class EraBlocks(M):
    merge: Annotated[dict[str, Annotated[list[str], Field(min_length=1)]], Field(min_length=1)]
    unknown: str
    route_merge_min_videos: PosInt


class DecisionDate(M):
    month: Annotated[int, Field(ge=1, le=12)]
    day: Annotated[int, Field(ge=1, le=31)]
    year_offset: Annotated[int, Field(ge=-1, le=0)]


class CompanyKey(M):
    salt: Annotated[str, Field(min_length=8)]
    length: Annotated[int, Field(ge=8, le=64)]


class Manifest(M):
    decision_date: dict[Literal["W", "X", "S", "F"], DecisionDate]
    company_key: CompanyKey

    @field_validator("decision_date")
    @classmethod
    def _all_seasons(cls, v):
        if set(v) != {"W", "X", "S", "F"}:
            raise ValueError("decision_date needs exactly the seasons W, X, S, F")
        return v


class Budget(M):
    usd_file: str
    ssm_parameter: Annotated[str, Field(pattern=r"^/yct/owner/")]
    default_usd: Pos
    alert_fraction: Frac
    max_hours_per_instance: Annotated[float, Field(gt=0, le=4)]


class Seeds(M):
    company_pick_salt: str
    controls_perm: PosInt             # D-071
    controls_boot: PosInt             # D-071
    refclips: PosInt                  # D-071 (b)


# ---------------------------------------------------------------- normalize (P2)
class BlackDetect(M):
    min_duration_s: Pos
    pix_th: Frac
    pic_th: Frac


class SilenceDetect(M):
    noise_db: float
    min_duration_s: Pos


class Video(M):
    codec: str
    crf: Annotated[int, Field(ge=0, le=51)]
    preset: str
    pix_fmt: str
    threads: PosInt


class Audio(M):
    codec: str
    sample_rate: PosInt
    bitrate: Annotated[str, Field(pattern=r"^\d+k$")]


class SidecarWav(M):
    sample_rate: PosInt
    channels: PosInt
    subdir: str


class Loudness(M):
    target_lufs: float
    true_peak_dbtp: float
    target_lra: Pos
    tolerance_lu: Pos
    tp_tolerance_db: NonNeg
    min_speech_s: NonNeg


class MonoPhase(M):
    max_drop_db: Pos
    drop_cap_db: Pos


class AvSync(M):
    max_offset_ms: Pos


class QualityFloor(M):
    short_side_px: PosInt
    crf: Annotated[int, Field(ge=0, le=51)]
    subdir: str


class Aspect(M):
    portrait_max_ratio: Pos


class TemporalSmoothing(M):
    enabled: bool
    size_frames: Annotated[int, Field(ge=2)]


class Photometric(M):
    enabled: bool
    subdir: str
    analysis_fps: Pos
    luma_weights: Annotated[list[float], Field(min_length=3, max_length=3)]
    gray_world: bool
    target_mean_y: Frac
    target_rms_contrast: Frac
    stats_region: Literal["vjepa_crop", "full_frame"]
    max_gain: Pos
    min_gain: Pos
    max_clip_frac: Frac
    crf: Annotated[int, Field(ge=0, le=51)]
    temporal_smoothing: TemporalSmoothing
    color_matrix: Literal["bt709"]
    color_range: Literal["tv"]
    sws_flags: list[Literal["accurate_rnd", "full_chroma_int", "bitexact", "full_chroma_inp"]]

    @field_validator("luma_weights")
    @classmethod
    def _bt709(cls, v):
        if abs(sum(v) - 1.0) > 1e-6:
            raise ValueError("luma_weights must sum to 1")
        return v

    @model_validator(mode="after")
    def _gains(self):
        if not self.min_gain < 1.0 < self.max_gain:
            raise ValueError("need min_gain < 1 < max_gain")
        return self


class UntaggedColor(M):
    hd_min_long_px: PosInt
    sd_max_short_px: PosInt
    hd: Literal["bt709"]
    sd: Literal["smpte170m", "bt470bg"]
    range: Literal["tv"]


class Hdr(M):                       # ENH-006
    transfers: Annotated[list[str], Field(min_length=1)]
    action: Literal["tonemap", "fail"]
    tonemap: Literal["hable", "mobius", "reinhard", "clip", "linear", "gamma"]
    desat: NonNeg
    npl: Pos
    untagged_matrix: str
    untagged_primaries: str
    covariate: Literal["hdr_source"]


class Color(M):
    matrix: Literal["bt709"]        # BT.709 everywhere (G-D032 c3 Neuro G1/N4, D-053)
    primaries: Literal["bt709"]
    transfer: Literal["bt709"]
    range: Literal["tv"]
    sws_flags: list[Literal["accurate_rnd", "full_chroma_int", "bitexact", "full_chroma_inp"]]   # ENH-005
    untagged: UntaggedColor
    hdr: Hdr


class Normalize(M):
    hash_len: Annotated[int, Field(ge=8, le=64)]
    edge_tolerance_s: NonNeg
    trim_mode: Literal["both", "either"]
    blackdetect: BlackDetect
    silencedetect: SilenceDetect
    video: Video
    audio: Audio
    sidecar_wav: SidecarWav
    loudness: Loudness
    mono_phase: MonoPhase
    av_sync: AvSync
    quality_floor: QualityFloor
    aspect: Aspect
    ffmpeg_loglevel: Literal["quiet", "panic", "fatal", "error", "warning", "info"]
    color: Color
    photometric: Photometric


class Vad(M):
    sample_rate: PosInt
    frame_s: Pos
    hop_s: Pos
    abs_floor_dbfs: float
    rel_db: Pos
    ref_percentile: Annotated[float, Field(gt=0, le=100)]
    min_gap_s: NonNeg
    min_seg_s: NonNeg


# ---------------------------------------------------------------- transcribe / confounds
class WhisperX(M):
    executable: str
    version: str | None
    model: str
    language: str
    device: str
    compute_type: str
    batch_size: PosInt
    align_model: str


class Wer(M):                         # D-063 Q5
    n_hand_checked: PosInt
    action_threshold: Frac
    rule: Literal["any_video"]


class Transcribe(M):
    whisperx: WhisperX
    wer: Wer
    tsv_columns: list[str]
    max_unmatched_ratio: Frac
    end_tolerance_s: NonNeg
    manifest_columns: list[str]


class Pitch(M):
    frame_s: Pos
    hop_s: Pos
    fmin_hz: Pos
    fmax_hz: Pos
    voicing_threshold: Frac
    octave_ratio: Frac


class Face(M):
    detector: str
    scale_factor: Annotated[float, Field(gt=1)]
    min_neighbors: PosInt
    min_size_frac: Frac
    crop_min_inside_frac: Frac


class Scene(M):
    detector: str
    threshold: Pos
    min_scene_len_frames: PosInt


class Confounds(M):
    rms_floor_db: float
    pitch: Pitch
    video_fps: Pos
    face_fps: Pos
    analysis_short_side_px: PosInt
    face: Face
    ffc_regressor: str
    scene: Scene
    text_detection: bool


# ---------------------------------------------------------------- atlases / features
class AnnotFile(M):
    file: str
    sha256: Sha256
    url: str | None = None
    md5: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")] | None = None

    @field_validator("url")
    @classmethod
    def _pinned(cls, v):
        # BUG/Watchdog G-D032 c2 #3: no moving branch refs; GitHub raw URLs must name a full commit sha.
        if v is None:
            return v
        if re.search(r"/(master|main|HEAD)/", v):
            raise ValueError(f"atlas URL must be pinned, not a branch: {v}")
        if "githubusercontent.com" in v and not re.search(r"/[0-9a-f]{40}/", v):
            raise ValueError(f"GitHub atlas URL must contain a full commit sha: {v}")
        return v


class Parcellation(M):
    source: str
    mesh: Literal["fsaverage", "fsaverage5"]
    lh: AnnotFile
    rh: AnnotFile


class Yeo7(M):
    networks: Annotated[list[str], Field(min_length=7, max_length=7)]


class Atlases(M):
    cache_dir: str
    n_vertices_per_hemi: Literal[10242]
    schaefer400_7: Parcellation
    yeo7: Yeo7
    hcp_mmp1: Parcellation
    destrieux: Parcellation


class Features(M):
    m1_networks: list[str]
    m1_reference: str
    standardize_ddof: Literal[0, 1]
    spatial_sd_ddof: Literal[0, 1]
    medial_wall: Literal["union"]


class MergeStep(M):
    name: str
    members: Annotated[list[str], Field(min_length=2)]
    why: str


class M0Covariates(M):
    forced: list[str]
    sensitivity: list[str]
    binary: list[str]
    linear_only: list[str]
    lag_impute: Literal["median"]
    predecision_max_lag_days: int

    @model_validator(mode="after")
    def _consistent(self):
        allc = set(self.forced) | set(self.sensitivity)
        if set(self.forced) & set(self.sensitivity):
            raise ValueError("a covariate is forced or sensitivity-only, not both")
        if set(self.binary) | set(self.linear_only) != allc or set(self.binary) & set(self.linear_only):
            raise ValueError("every covariate is exactly one of binary / linear_only")
        if "upload_lag_days" in self.forced:
            raise ValueError("upload_lag_days is sensitivity-only (D-053, Referee G-D032 c3 N2)")
        return self


class M0(M):
    features: Annotated[list[str], Field(min_length=1)]
    never: list[str]
    binary: list[str]
    forced_speech: Annotated[list[str], Field(min_length=2, max_length=2)]
    covariates: M0Covariates
    min_words_in_w: PosInt
    q_rule: str
    z_ddof: Literal[0, 1]
    rank_rcond: Pos
    max_cond: Pos
    merge_list: list[MergeStep]

    @model_validator(mode="after")
    def _consistent(self):
        if set(self.never) & set(self.features):
            raise ValueError("m0.never features must not be in m0.features")
        if not set(self.forced_speech) <= set(self.features):
            raise ValueError("m0.forced_speech must be m0.features")
        for step in self.merge_list:
            if set(step.members) & set(self.forced_speech):
                raise ValueError("forced speech features are never merged")
        return self


class ReliabilityMask(M):
    source: str
    rule: str
    atlas: Literal["hcp_mmp1"]
    areas: Annotated[list[str], Field(min_length=1)]
    hemis: Annotated[list[Literal["L", "R"]], Field(min_length=1)]
    n_vertices: PosInt
    sha256: Sha256


class Localize(M):
    top_k: PosInt
    ci_level: Annotated[float, Field(gt=0, lt=1)]
    views: list[Literal["lateral", "medial", "ventral", "dorsal", "anterior", "posterior"]]
    bootstrap_B: Annotated[int, Field(ge=1000)]  # noqa: N815 - config key
    unreliable_parcel_max_frac: Frac
    reliability_mask: ReliabilityMask
    hcp_second_below: Frac
    unreliable_pattern: Annotated[list[Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]],
                                  Field(min_length=2, max_length=2)]
    stipple_cell_mm: Pos
    dpi: PosInt
    mw_shrink_flag_frac: Frac
    mw_shrunk_parcels: list[str]
    caption: str
    banned_patterns: list[str]

    @field_validator("banned_patterns")
    @classmethod
    def _regex(cls, v):
        for p in v:
            re.compile(p)
        return v


# ---------------------------------------------------------------- P4b controls
class Roi(M):
    areas: Annotated[list[str], Field(min_length=1)]
    hemis: list[Literal["L", "R"]]
    n_vertices: PosInt


class Regressor(M):
    source: Literal["confounds", "derived"]
    roi: str
    column: str | None = None
    from_: str | None = Field(default=None, alias="from")
    op: str | None = None
    gating: bool                      # D-063 Q4: true = can STOP P4b; false = partialled out / reported only


class Descriptive(M):
    regressor: str
    roi: str


Pair = Annotated[list[int], Field(min_length=2, max_length=2)]
Gate = Literal["stop", "descriptive"]


class K1(M):
    alpha: Frac
    sign_all_positive: bool
    ffc_min_positive_frac: Frac


class K1p(M):
    min_frac_sigma_nat: Pos
    min_abs: Pos


class K2(M):
    window: Pair
    plateau_frac: Frac
    crossing_window: Pair
    crossing_frac: Frac
    tail_lags: Pair
    tail_frac: Frac


class K3(M):
    baseline_lags: Pair
    min: Pos


class K3p(M):
    span: Pair
    max_frac_peak: Frac
    alpha_two_sided: Frac


class K4a(M):
    min_median_r: Annotated[float, Field(ge=-1, le=1)]


class K4b(M):
    min_r: Annotated[float, Field(ge=-1, le=1)]


class K5(M):
    lags: Pair
    min_abs_frac_peak: Frac
    max_lag_diff: Annotated[int, Field(ge=0)]


class K6(M):
    lags: Pair
    roi: str


class Acceptance(M):                  # D-071 (f)/(g)
    peak: str
    K1: K1
    K1p: K1p
    K2: K2
    K3: K3
    K3p: K3p
    K4a: K4a
    K4b: K4b
    K5: K5
    K6: K6
    on_fail: dict[Literal["FFC", "AUD", "AUD_audioonly", "MT_plus"], Gate]
    on_stop_invalid: Literal["stop"]
    demotion_final: bool


class Kernel(M):
    type: str
    window_tr: Pair
    min_reference_clips: PosInt
    shift_by_L: bool  # noqa: N815 - config key
    acceptance: Acceptance


class DryRun(M):
    reference_clips_min: PosInt
    talking_face_clip: bool
    n_flashes: PosInt
    n_speech_bursts: PosInt


class PassA(M):                       # D-071 (i)(a)
    mean_z_min: float
    alpha: Frac
    z_clip: Annotated[float, Field(gt=0, lt=1)]
    low_sd_pctile: Annotated[float, Field(ge=0, le=100)]
    min_videos: PosInt


class PassB(M):
    alpha: Frac


class PassC(M):
    r_min: float
    alpha: Frac
    n_perm: PosInt
    route_blocks: Literal[False]


class PassD(M):
    n_boot: PosInt
    ci: Frac


class Pass(M):                        # D-071: replaces the v2.5 within_video/selectivity/between_video block
    a: PassA
    b: PassB
    c: PassC
    d: PassD


class RefClips(M):                    # D-071 (a)-(e), (k)
    version: str
    s3_root: Annotated[str, Field(pattern=r"^s3://yct-research-235229001983/wave1/derived/p4b_ref/v\d+/$")]
    campaign_cap_usd: Pos
    campaign_warn_usd: Pos
    ledger_name_prefix: Annotated[str, Field(pattern=r"^yct-p4b-ref")]
    onsets_s: list[float]
    shift_rule: str
    families: dict[str, PosInt]
    mot_directions_deg: list[int]
    mot_direction_rule: str
    mot_pattern_rule: str
    loc_categories: list[Literal["face", "body", "place"]]
    loc_latin_rule: str
    loc_per_category: PosInt
    nat_n: PosInt
    image_licences: list[str]
    image_queries: dict[Literal["face", "body", "place"], list[str]]
    nat_query: str
    snapshot_limits: dict[Literal["image", "nat"], PosInt]
    reject_reasons: list[str]
    greyscale: Literal["bt709_luma"]
    shine: dict[str, Any]
    job_order: list[list[str]]

    @model_validator(mode="after")
    def _cap(self):
        if not self.campaign_warn_usd < self.campaign_cap_usd:
            raise ValueError("controls.refclips.campaign_warn_usd must be below campaign_cap_usd")
        return self


class RefClipArtifacts(M):            # D-071 (d): null until set; frozen row per key once set
    image_snapshot_sha256: Sha256 | None
    nat_snapshot_sha256: Sha256 | None
    image_manifest_sha256: Sha256 | None
    nat_manifest_sha256: Sha256 | None
    manifest_sha256: Sha256 | None


class RefClipsD078Artifacts(M):       # D-078
    body_snapshot_sha256: Sha256 | None


class D074Source(M):                  # D-074
    category: Annotated[str, Field(min_length=1)]
    depth: Literal[0]


class RefClipsD074(M):                # D-074: Commons category candidate source for localiser images
    decision: Literal["D-074"]
    image_sources: dict[Literal["face", "body", "place"], Annotated[list[D074Source], Field(min_length=1)]]
    namespace: Literal[6]
    api: Literal["generator=categorymembers&gcmtype=file&gcmnamespace=6&prop=info|imageinfo"
                 "&iiprop=mime|mediatype|sha1|size"]
    bitmap_mediatype: Literal["BITMAP"]
    image_snapshot_limit: PosInt
    require_complete: Literal[True]
    snapshot_file_suffix: Literal["_d074"]


class RefClipsD078(M):                # D-078: second body category (amends D-074)
    decision: Literal["D-078"]
    amends: Literal["D-074"]
    categories: list[Literal["body"]]
    image_sources: dict[Literal["body"], Annotated[list[D074Source], Field(min_length=2)]]
    base: Literal["frozen_d074_snapshot"]
    selection: Literal["union_sha256_title_from_start"]
    snapshot_file_suffix: Literal["_d078"]
    log_suffix: Literal["_d078"]
    audit_exempt_reasons: list[Literal["duplicate"]]


class D079Audit(M):                   # D-079
    exempt_reasons: list[Literal["duplicate"]]
    c1_reasons: list[Literal["licence", "personality_rights"]]
    flip_file: Literal["data/refstim/bug036_c1_flips.json"]


class D079StopResolution(M):          # D-079 re-check B1
    identity_mismatch: Literal["reject_identity_changed_resume_next_rank"]
    lastrevid_moved: Literal["retry_batch_once_then_stop_to_council"]
    other_audit_stop: Literal["code_defect_bug_entry_v3_from_rank_1"]


class RefClipsD079(M):                # D-079: v2 image logs after BUG-036 (amends D-074/D-075/D-078)
    decision: Literal["D-079"]
    amends: list[Literal["D-074", "D-075", "D-078"]]
    log_version: Literal["v2"]
    category_order: list[Literal["face", "body", "place"]]
    logs: dict[Literal["face", "body", "place"], Annotated[str, Field(pattern=r"_v2\.jsonl$")]]
    superseded_logs: dict[Literal["face", "body", "place"], list[str]]
    audit: D079Audit
    revid_rule: Literal["evaluate_current_log_both"]
    identity_rule: Literal["reject_identity_changed"]
    extra_reject_reasons: list[Literal["identity_changed"]]
    stop_resolution: D079StopResolution
    finality: Literal["v2_is_selection"]


class RefClipsD079Artifacts(M):       # D-079
    flip_sha256: Sha256 | None


class D080StopResolution(M):          # D-080 council watchdog B1
    audit_revid_drift: Literal["current_revision_stands_log_both_resume_next_rank"]


class RefClipsD080(M):                # D-080 draft (BUG-037): v3 logs, C1-equivalence in the audit
    decision: Literal["D-080"]
    amends: list[Literal["D-079"]]
    log_version: Literal["v3"]
    logs: dict[Literal["face", "body", "place"], Annotated[str, Field(pattern=r"_v3\.jsonl$")]]
    superseded_logs_add: dict[Literal["face", "body", "place"], list[str]]
    audit_c1_equivalence: Literal[True]
    dry_audit_file: Literal["data/refstim/d080_dry_audit.json"]
    stop_resolution: D080StopResolution
    finality: Literal["v3_is_selection"]


class RefClipsD080Artifacts(M):       # D-080
    dry_audit_sha256: Sha256 | None


class RefClipsD081(M):                # D-081 draft (BUG-038): v4 logs from rank 1; rule-based C1 audit
    decision: Literal["D-081"]
    amends: list[Literal["D-080"]]
    log_version: Literal["v4"]
    logs: dict[Literal["face", "body", "place"], Annotated[str, Field(pattern=r"_v4\.jsonl$")]]
    superseded_logs_add: dict[Literal["face", "body", "place"], list[str]]
    dry_audit_file: Literal["data/refstim/d081_dry_audit.json"]
    reaudit_file: Literal["data/refstim/d081_reaudit.json"]
    finality: Literal["v4_is_selection"]


class D082Plda(M):
    repo: Literal["pyannote/speaker-diarization-community-1"]
    revision: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    subfolder: Literal["plda"]
    files: list[Literal["plda.npz", "xvec_transform.npz"]]


class RefClipsD082(M):                # D-082 draft (BUG-040): pinned community-1 PLDA for pyannote 4.1.0
    decision: Literal["D-082"]
    amends: list[Literal["D-075"]]
    plda: D082Plda
    clustering_must_be: Literal["AgglomerativeClustering"]


class RefClipsD081Artifacts(M):       # D-081
    dry_audit_sha256: Sha256 | None
    reaudit_sha256: Sha256 | None


class AutoEnv(M):                     # D-075
    where: Literal["yct_pod_cpu"]
    python: Literal["3.12.3"]
    lock: Literal["infra/refstim_env.lock"]
    packages: dict[str, str]
    tesseract: dict[str, str]


class AutoFaceDetector(M):
    impl: Literal["cv2.FaceDetectorYN"]
    repo: Literal["opencv/opencv_zoo"]
    revision: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    file: Literal["models/face_detection_yunet/face_detection_yunet_2023mar.onnx"]
    input_long_side: Literal[640]
    score_threshold: Literal[0.9]
    nms_threshold: Literal[0.3]
    top_k: Literal[5000]
    exclusion_score_threshold: Literal[0.5]


class AutoEyeDetector(M):
    cascade: Literal["haarcascade_eye.xml"]
    scale_factor: Literal[1.1]
    min_neighbors: Literal[5]
    min_count: Literal[2]
    region: Literal["upper_half_of_yunet_box_original_image"]


class AutoPersonDetector(M):
    impl: Literal["torchvision.models.detection.fasterrcnn_resnet50_fpn_v2"]
    weights: Literal["COCO_V1"]
    url: Literal["https://download.pytorch.org/models/fasterrcnn_resnet50_fpn_v2_coco-dd69338a.pth"]
    person_class: Literal[1]
    score_threshold: Literal[0.5]
    input_long_side: Literal[1600]


class AutoOcr(M):
    impl: Literal["tesseract"]
    psm: Literal[11]
    oem: Literal[1]
    min_conf: Literal[60]
    max_text_area_frac: Literal[0.01]
    image_long_side: Literal[1600]


class AutoClip(M):
    model: Literal["ViT-B-32"]
    pretrained: Literal["laion2b_s34b_b79k"]
    hf_repo: Literal["laion/CLIP-ViT-B-32-laion2B-s34B-b79K"]
    revision: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    file: Literal["open_clip_pytorch_model.bin"]
    photo_prompts: list[str]
    adult_prompts: list[str]
    decision: Literal["argmax"]

    @model_validator(mode="after")
    def _prompts(self):
        if self.photo_prompts[0] != "a photograph" or self.adult_prompts != ["a photo of a child",
                                                                             "a photo of an adult"]:
            raise ValueError("refclips_auto.clip prompts: photo first; adult = [child, adult]")
        return self


class AutoHeadpose(M):
    solver: Literal["SQPNP"]
    landmark_order: list[Literal["right_eye", "left_eye", "nose_tip", "right_mouth_corner",
                                 "left_mouth_corner"]]
    model_points_mm: Annotated[list[Annotated[list[float], Field(min_length=3, max_length=3)]],
                               Field(min_length=5, max_length=5)]
    focal: Literal["image_width_640_long_side"]
    max_abs_yaw_deg: Literal[20]
    max_abs_pitch_deg: Literal[20]


class AutoNatLang(M):
    impl: Literal["faster_whisper.WhisperModel.detect_language"]
    faster_whisper: Literal["1.2.1"]
    model: Literal["large-v3"]
    samples_s: Annotated[list[int], Field(min_length=2, max_length=2)]
    audio: Literal["trimmed_t1"]
    min_prob_en: Literal[0.9]


class AutoNatDiar(M):
    pipeline: Literal["pyannote/speaker-diarization-3.1"]
    revision: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    segmentation: str
    embedding: str
    pyannote_audio: Literal["4.1.0"]
    audio: Literal["trimmed_t1"]
    min_main_speaker_frac: Literal[0.95]
    max_other_speaker_s: Literal[3.0]
    zero_speech: Literal["not_single_speaker"]


class AutoNat(M):
    cpu_buffer: Literal[40]
    lang_id: AutoNatLang
    diarization: AutoNatDiar
    stage: Literal["session_0"]
    counts_toward_cap: Literal[True]
    weights_mirror: Literal["models/"]


class RefClipsAuto(M):                # D-075: frozen automatic filters (owner decisions 2026-11-20)
    decision: Literal["D-075"]
    supersedes: str
    env: AutoEnv
    face_detector: AutoFaceDetector
    eye_detector: AutoEyeDetector
    person_detector: AutoPersonDetector
    ocr: AutoOcr
    clip: AutoClip
    headpose: AutoHeadpose
    face_rules: dict[Literal["min_face_height_frac_crop", "min_interocular_frac_box"], float]
    body_rules: dict[Literal["min_person_area_frac"], float]
    common: dict[str, Any]
    rule_reasons: dict[str, str | list[str]]
    image_artifacts: list[str]
    logs: dict[Literal["image", "nat"], str]
    nat: AutoNat
    determinism: dict[Literal["torch_seed", "threads"], int]


class CurationHttp(M):               # owner decision 2026-11-20
    user_agent: Annotated[str, Field(pattern=r"^yct-research/[0-9.]+ \(https://github\.com/ArioMoniri/yct\)$")]
    min_interval_s: Annotated[float, Field(ge=1.0)]
    backoff_base_s: Annotated[float, Field(gt=0)]
    max_429_wait_s: Annotated[int, Field(gt=0, le=1800)]


class RefClipsAutoArtifacts(M):       # D-075: null until set (commit k); frozen row at k+1
    yunet_sha256: Sha256 | None
    frcnn_sha256: Sha256 | None
    clip_sha256: Sha256 | None
    tessdata_eng_sha256: Sha256 | None
    haar_face_sha256: Sha256 | None
    haar_eye_sha256: Sha256 | None
    pyannote_diarization_sha256: Sha256 | None
    pyannote_segmentation_sha256: Sha256 | None
    pyannote_embedding_sha256: Sha256 | None
    pyannote_plda_sha256: Sha256 | None     # D-082 draft


class Controls(M):
    rois: dict[str, Roi]
    regressors: dict[str, Regressor]
    partial_out: list[str]
    kernel: Kernel
    aud_selectivity_run: str
    readout_lag_tr: Annotated[list[int], Field(min_length=2, max_length=2)]
    maps: list[Literal["spatially_standardised", "raw"]]
    dry_run: DryRun
    pass_: Pass = Field(alias="pass")
    descriptive: list[Descriptive]
    rois_per_hemi: dict[str, Pair]
    mw_removed_frac: dict[str, Frac]
    refclips: RefClips
    refclips_artifacts: RefClipArtifacts
    refclips_d074: RefClipsD074
    refclips_d078: RefClipsD078
    refclips_d078_artifacts: RefClipsD078Artifacts
    refclips_d079: RefClipsD079
    refclips_d079_artifacts: RefClipsD079Artifacts
    refclips_d080: RefClipsD080
    refclips_d080_artifacts: RefClipsD080Artifacts
    refclips_d081: RefClipsD081
    refclips_d081_artifacts: RefClipsD081Artifacts
    refclips_d082: RefClipsD082
    curation_http: CurationHttp
    refclips_auto: RefClipsAuto
    refclips_auto_artifacts: RefClipsAutoArtifacts

    @model_validator(mode="after")
    def _refs(self):
        for name, r in self.regressors.items():
            if r.roi not in self.rois:
                raise ValueError(f"controls.regressors.{name}.roi {r.roi!r} is not a defined ROI")
        for d in self.descriptive:
            if d.regressor not in self.regressors or d.roi not in self.rois:
                raise ValueError(f"controls.descriptive {d} names an undefined regressor or ROI")
        if not set(self.partial_out) <= set(self.regressors):
            raise ValueError("controls.partial_out names an undefined regressor")
        for name, (left, right) in self.rois_per_hemi.items():
            if name not in self.rois or left + right != self.rois[name].n_vertices:
                raise ValueError(f"controls.rois_per_hemi.{name} must sum to controls.rois.{name}.n_vertices")
        if set(self.mw_removed_frac) != set(self.rois_per_hemi):
            raise ValueError("controls.mw_removed_frac must list the same ROIs as rois_per_hemi")
        if self.kernel.acceptance.K6.roi not in self.rois:
            raise ValueError("controls.kernel.acceptance.K6.roi is not a defined ROI")
        if set(self.refclips_d074.image_sources) != set(self.refclips.loc_categories):
            raise ValueError("controls.refclips_d074.image_sources must cover exactly "
                             "refclips.loc_categories")
        if set(self.refclips_d078.categories) != set(self.refclips_d078.image_sources):
            raise ValueError("controls.refclips_d078.categories must equal its image_sources keys")
        for c in self.refclips_d078.categories:
            if self.refclips_d078.image_sources[c][0] != self.refclips_d074.image_sources[c][0]:
                raise ValueError(f"controls.refclips_d078.image_sources.{c} must start with the D-074 source")
        d9 = self.refclips_d079
        if d9.category_order != self.refclips.loc_categories or set(d9.logs) != set(d9.category_order) \
                or set(d9.superseded_logs) != set(d9.category_order):
            raise ValueError("controls.refclips_d079 must route exactly refclips.loc_categories, in order")
        if set(d9.logs.values()) & {p for v in d9.superseded_logs.values() for p in v}:
            raise ValueError("controls.refclips_d079: a v2 log path is a superseded v1 log")
        d8 = self.refclips_d080
        if set(d8.logs) != set(d9.category_order) or set(d8.superseded_logs_add) != set(d9.category_order):
            raise ValueError("controls.refclips_d080 must route exactly refclips.loc_categories")
        old = {p for v in d9.superseded_logs.values() for p in v} | set(d9.logs.values())
        if set(d8.logs.values()) & old:
            raise ValueError("controls.refclips_d080: a v3 log path is a v1/v2 log")
        if any(set(v) - {d9.logs[c]} for c, v in d8.superseded_logs_add.items()):
            raise ValueError("controls.refclips_d080.superseded_logs_add may only name D-079 v2 logs")
        d81 = self.refclips_d081
        if set(d81.logs) != set(d9.category_order) or set(d81.superseded_logs_add) != set(d9.category_order):
            raise ValueError("controls.refclips_d081 must route exactly refclips.loc_categories")
        if set(d81.logs.values()) & (old | set(d8.logs.values())):
            raise ValueError("controls.refclips_d081: a v4 log path is a v1/v2/v3 log")
        if any(set(v) - {d8.logs[c]} for c, v in d81.superseded_logs_add.items()):
            raise ValueError("controls.refclips_d081.superseded_logs_add may only name D-080 v3 logs")
        reasons = set(self.refclips.reject_reasons)
        if set(d9.extra_reject_reasons) & reasons:
            raise ValueError("controls.refclips_d079.extra_reject_reasons repeats a frozen "
                             "reject_reasons entry")
        for rule, rs_ in self.refclips_auto.rule_reasons.items():
            for r in (rs_ if isinstance(rs_, list) else [rs_]):
                if r not in reasons:
                    raise ValueError(f"controls.refclips_auto.rule_reasons.{rule}: {r!r} not in "
                                     "reject_reasons")
        arts = set(type(self.refclips_auto_artifacts).model_fields)
        if not set(self.refclips_auto.image_artifacts) <= arts:
            raise ValueError("controls.refclips_auto.image_artifacts names an undefined artifact key")
        return self


# ---------------------------------------------------------------- P4 run sets (D-063)
VideoId = Annotated[str, Field(pattern=r"^yct_\d{4}$")]


class LowFps(M):
    rule: str
    videos: list[VideoId]
    sensitivity: str


class P4Flags(M):
    low_fps_source: LowFps


class P4(M):
    decision: Literal["D-063"]
    analysis_excluded: dict[VideoId, str]
    t1_excluded: dict[VideoId, str]
    run_set_t3: Annotated[list[VideoId], Field(min_length=1)]
    run_set_t1: Annotated[list[VideoId], Field(min_length=1)]
    flags: P4Flags
    d038_clips: list[VideoId]
    gpu_type: str
    gpu_name: str
    s3_prefix: Annotated[str, Field(pattern=r"^s3://yct-research-235229001983/")]
    superseded_run_ids: list[Annotated[str, Field(pattern=r"^[A-Za-z0-9_]+$")]]   # BUG-029, D-067 (required)
    session_max_hours: Annotated[float, Field(gt=0, le=4)]
    launcher_max_hours: Annotated[float, Field(gt=0, le=4)]   # BUG-028 (config value tested < 2)
    terminator_margin_s: PosInt

    @model_validator(mode="after")
    def _sets(self):
        for name in ("run_set_t3", "run_set_t1"):
            v = getattr(self, name)
            if v != sorted(set(v)):
                raise ValueError(f"p4.{name} must be sorted and unique")
        if set(self.analysis_excluded) & set(self.run_set_t3):
            raise ValueError("p4.run_set_t3 contains an excluded video")
        if set(self.run_set_t1) != set(self.run_set_t3) - set(self.t1_excluded):
            raise ValueError("p4.run_set_t1 must equal run_set_t3 minus t1_excluded")
        if not set(self.d038_clips) <= set(self.run_set_t1):
            raise ValueError("p4.d038_clips must be T1 run-set videos")
        if not set(self.flags.low_fps_source.videos) <= set(self.run_set_t3):
            raise ValueError("p4.flags.low_fps_source.videos must be run-set videos")
        return self


# ---------------------------------------------------------------- guards / owner / frozen
class AllowEntry(M):
    commit: Sha1
    path: str
    kind: Literal["skip", "assertion", "testdef", "threshold"]
    ticket: Annotated[str, Field(pattern=r"^(BUG|ENH)-\d{3,}$")]
    note: str | None = None


class ExemptEntry(M):
    commit: Sha1
    path: Literal["UNBLIND_TOKEN", "infra/BUDGET_USD", "docs/owner_age.pub", "DATA_DECISION.md"]
    ticket: Annotated[str, Field(pattern=r"^(BUG|ENH)-\d{3,}$")]
    note: str | None = None


class Guards(M):
    human_only_exempt: list[ExemptEntry]
    test_weakening_allowlist: list[AllowEntry]
    human_signed_since: Sha1 | None = None


class Owner(M):
    arn_pin: Annotated[str, Field(pattern=r"^arn:aws:(iam|sts)::\d{12}:\S+$")]


class Frozen(M):
    key: str
    frozen_at: Sha1


class Config(M):
    schema_version: Literal[1]
    tribe: Tribe
    stimulus: Stimulus
    window: Window
    era_strata: dict[str, Era]
    era_merge_min_videos: PosInt
    era_blocks: EraBlocks
    manifest: Manifest
    budget: Budget
    seeds: Seeds
    normalize: Normalize
    vad: Vad
    transcribe: Transcribe
    confounds: Confounds
    atlases: Atlases
    features: Features
    m0: M0
    localize: Localize
    controls: Controls
    p4: P4
    guards: Guards
    owner: Owner
    frozen: list[Frozen]

    @model_validator(mode="after")
    def _era_blocks_partition_strata(self):
        members = [s for ms in self.era_blocks.merge.values() for s in ms]
        if sorted(members) != sorted(self.era_strata):
            raise ValueError(f"era_blocks.merge {members} must list every era_strata key exactly once")
        if self.era_blocks.unknown in self.era_blocks.merge:
            raise ValueError("era_blocks.unknown must not also be a merged block name")
        return self


def validate_config(cfg: dict[str, Any]) -> Config:
    """Raise pydantic.ValidationError unless cfg matches the schema exactly."""
    return Config.model_validate(cfg)
