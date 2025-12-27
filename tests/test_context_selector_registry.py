from tpa_api.spec_io import _read_yaml, _spec_root


REQUIRED_WORK_MODES = {"plan_studio", "casework", "pre_app", "nsip"}
KNOWN_SLICE_TYPES = {
    "policy_clauses",
    "evidence_atoms",
    "visual_assets",
    "spatial_features",
    "consultations",
    "decisions",
    "advice_cards",
    "assumptions",
    "limitations",
}


def _load_registry() -> dict:
    path = (_spec_root() / "capabilities" / "CONTEXT_SELECTOR_REGISTRY.yaml").resolve()
    data = _read_yaml(path)
    return data if isinstance(data, dict) else {}


def _load_move_io() -> dict:
    path = (_spec_root() / "grammar" / "MOVE_IO_CATALOGUE.yaml").resolve()
    data = _read_yaml(path)
    return data if isinstance(data, dict) else {}


def _selectors_by_key(registry: dict) -> dict[tuple[str, str], dict]:
    selectors = registry.get("selectors") if isinstance(registry.get("selectors"), list) else []
    by_key: dict[tuple[str, str], dict] = {}
    for selector in selectors:
        if not isinstance(selector, dict):
            continue
        work_mode = selector.get("work_mode")
        move_type = selector.get("move_type")
        if isinstance(work_mode, str) and isinstance(move_type, str):
            by_key[(work_mode, move_type)] = selector
    return by_key


def _required_slices_by_move(move_io: dict) -> dict[str, set[str]]:
    moves = move_io.get("moves") if isinstance(move_io.get("moves"), dict) else {}
    required: dict[str, set[str]] = {}
    for move_type, spec in moves.items():
        if not isinstance(spec, dict):
            continue
        deps = spec.get("context_pack_dependencies") if isinstance(spec.get("context_pack_dependencies"), dict) else {}
        req = deps.get("required") if isinstance(deps.get("required"), list) else []
        required[str(move_type)] = {s for s in req if isinstance(s, str)}
    return required


def test_context_selector_coverage() -> None:
    registry = _load_registry()
    move_io = _load_move_io()
    selectors = _selectors_by_key(registry)
    moves = move_io.get("moves") if isinstance(move_io.get("moves"), dict) else {}

    missing: list[str] = []
    for work_mode in sorted(REQUIRED_WORK_MODES):
        for move_type in sorted(moves.keys()):
            if (work_mode, move_type) not in selectors:
                missing.append(f"{work_mode}:{move_type}")

    assert not missing, f"Missing context selectors: {', '.join(missing)}"


def test_context_selector_required_slices_present() -> None:
    registry = _load_registry()
    move_io = _load_move_io()
    selectors = _selectors_by_key(registry)
    required_by_move = _required_slices_by_move(move_io)

    missing: list[str] = []
    for (work_mode, move_type), selector in selectors.items():
        required = required_by_move.get(move_type, set())
        slice_entries = selector.get("slices") if isinstance(selector.get("slices"), list) else []
        slice_types = {s.get("slice_type") for s in slice_entries if isinstance(s, dict)}
        if not required.issubset(slice_types):
            missing_slices = ", ".join(sorted(required - slice_types))
            missing.append(f"{work_mode}:{move_type} missing [{missing_slices}]")

    assert not missing, "Required slices missing: " + "; ".join(missing)


def test_context_selector_slice_types_known() -> None:
    registry = _load_registry()
    selectors = registry.get("selectors") if isinstance(registry.get("selectors"), list) else []

    unknown: list[str] = []
    for selector in selectors:
        if not isinstance(selector, dict):
            continue
        work_mode = selector.get("work_mode")
        move_type = selector.get("move_type")
        slices = selector.get("slices") if isinstance(selector.get("slices"), list) else []
        for entry in slices:
            if not isinstance(entry, dict):
                continue
            slice_type = entry.get("slice_type")
            if isinstance(slice_type, str) and slice_type not in KNOWN_SLICE_TYPES:
                unknown.append(f"{work_mode}:{move_type}:{slice_type}")

    assert not unknown, "Unknown slice types: " + ", ".join(unknown)
