"""回放对比打分：截图相似度 + 信号重叠（确定性，无 LLM）。"""
import io


def image_similarity(img_a: bytes, img_b: bytes) -> float:
    """两图缩到 64×64 灰度，算平均绝对差相似度 [0,1]。"""
    if not img_a or not img_b:
        return 0.0
    try:
        from PIL import Image

        a = Image.open(io.BytesIO(img_a)).convert("L").resize((64, 64)).tobytes()
        b = Image.open(io.BytesIO(img_b)).convert("L").resize((64, 64)).tobytes()
    except Exception:  # noqa: BLE001 解码失败按不可比处理
        return 0.0
    if len(a) != len(b) or not a:
        return 0.0
    diff = sum(abs(x - y) for x, y in zip(a, b)) / len(a)
    return round(max(0.0, 1.0 - diff / 255.0), 4)


def signal_overlap(original: list, replayed: list) -> bool:
    """原始信号是否在回放中复现（任意一条命中即可）。"""
    if not original:
        return False
    replayed_set = set(replayed)
    return any(sig in replayed_set for sig in original)
