import requests
import json

response = requests.post("http://localhost:5005/api/analyze", json={
    "process_id": "merchant-onboarding",
    "regulation_id": "synthetic-compliance-rules-#1",
    "strictness": "conservative"
}, timeout=600)

data = response.json()
segments = data.get("segments", [])
print(f"Total segments returned: {len(segments)}")
print()

for seg in segments:
    print(f"chunk_id:          '{seg.get('chunk_id')}'")
    print(f"category:          '{seg.get('category')}'")
    print(f"easy_rule:         '{seg.get('easy_rule')}'")
    print(f"s3_category_1:     '{seg.get('s3_category_1')}'")
    print(f"s3_category_2:     '{seg.get('s3_category_2')}'")
    print(f"s3_resolution:     '{seg.get('s3_resolution')}'")
    print(f"compliance_report: '{seg.get('compliance_report')}'")
    print("-" * 60)