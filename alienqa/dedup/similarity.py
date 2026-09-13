"""相似度：文本 2-gram Jaccard、截图 aHash、Hamming、向量 cosine（确定性）。"""
import io


def text_jaccard(a, b) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def ahash(image_bytes) -> int | None:
    """平均哈希：缩到 8×8 灰度，按均值阈值生成 64 位。"""
    if not image_bytes:
        return None
    try:
        from PIL import Image

        im = Image.open(io.BytesIO(image_bytes)).convert("L").resize((8, 8))
        pixels = list(im.tobytes())
    except Exception:  # noqa: BLE001
        return None
    if not pixels:
        return None
    avg = sum(pixels) / len(pixels)
    bits = "".join("1" if p >= avg else "0" for p in pixels)
    return int(bits, 2)


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def cosine(a, b) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)
