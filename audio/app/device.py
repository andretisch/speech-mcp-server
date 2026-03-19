import torch


def select_device() -> str:
    if not torch.cuda.is_available():
        return "cpu"

    try:
        count = torch.cuda.device_count()
    except Exception:
        return "cpu"

    best_idx = None
    best_cap = -1
    for i in range(max(0, int(count))):
        try:
            major, minor = torch.cuda.get_device_capability(i)
            cap = major * 10 + minor
        except Exception:
            continue
        if cap >= 70 and cap > best_cap:
            best_cap = cap
            best_idx = i

    if best_idx is None:
        return "cpu"

    try:
        torch.cuda.set_device(best_idx)
    except Exception:
        return "cpu"

    return "cuda"

