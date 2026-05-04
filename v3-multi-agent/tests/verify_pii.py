"""Security PII 掩码验证脚本。"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.security import filter_output

print("=" * 60)
print("验证: PII 个人信息掩码")
print("=" * 60)

text = "联系作者 13812345678 或 author@example.com 获取完整代码 · IP 192.168.1.1"
filtered, detections = filter_output(text, mask=True)

print(f"\n原文：{text}")
print(f"\n掩码：{filtered}")
print(f"\n检出：{len(detections)} 处")
for d in detections:
    print(f"  - {d['type']}: 检测到 1 处")

# 验证结果
assert len(detections) == 3, f"❌ 期望检测到 3 处 PII，实际 {len(detections)} 处"
assert "[PHONE_CN_MASKED]" in filtered, "❌ 手机号未正确掩码"
assert "[EMAIL_MASKED]" in filtered, "❌ 邮箱未正确掩码"
assert "[IP_ADDRESS_MASKED]" in filtered, "❌ IP 地址未正确掩码"

print("\n" + "=" * 60)
print("✅ PII 掩码验证通过！")
print("=" * 60)
