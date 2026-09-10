import os
import time

os.environ["IMAGE_REFERENCE_MAX_PER_CLASS"] = "1000"

from services.kaggle_reference import kaggle_reference

kaggle_reference.ensure_built("image")
deadline = time.time() + 90
while time.time() < deadline:
    time.sleep(2)
    if kaggle_reference.available("image"):
        break

p = kaggle_reference._profiles.get("image")
print("status:", kaggle_reference.status)
if p:
    print("slug:", p.slug)
    print("samples:", p.samples)
    print("real class mean:", {k: round(v[0], 3) for k, v in p.classes.get("real", {}).items()})
    print("fake class mean:", {k: round(v[0], 3) for k, v in p.classes.get("fake", {}).items()})
    score = kaggle_reference.score({
        "error_level_analysis": 0.17,
        "texture_uniformity": 0.19,
        "recompression_similarity": 0.99,
        "color_flatness": 0.12,
        "histogram_entropy": 8.9,
    })
    print("sample score:", score)
else:
    print("error:", kaggle_reference.error())