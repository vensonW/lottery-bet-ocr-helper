from __future__ import annotations


LOTTERY_OCR_SCHEMA = {
    "type": "object",
    "properties": {
        "image_file": {
            "type": "string",
            "description": "当前图片文件名",
        },
        "items": {
            "type": "array",
            "description": "图片中的投注行，按从上到下、从左到右顺序排列",
            "items": {
                "type": "object",
                "properties": {
                    "raw_text": {
                        "type": "string",
                        "description": "原图可见投注内容，不包含姓名",
                    },
                    "play_type": {
                        "type": "string",
                        "enum": ["胆码", "组三", "组六", "定位", "直选", "直选组选混合", "未知"],
                    },
                    "standardized": {
                        "type": "string",
                        "description": "按SKILL.md规则整理后的标准化结果；不确定时可为空",
                    },
                    "amount": {
                        "type": "integer",
                        "description": "金额，单位元；不确定填0并标记人工核查",
                    },
                    "needs_review": {
                        "type": "boolean",
                        "description": "是否需要人工核查",
                    },
                    "review_reason": {
                        "type": "string",
                        "description": "只有需要人工核查时填写具体原因；正常项为空字符串",
                    },
                    "crop_hint": {
                        "type": ["object", "null"],
                        "properties": {
                            "x": {"type": "integer"},
                            "y": {"type": "integer"},
                            "w": {"type": "integer"},
                            "h": {"type": "integer"},
                        },
                        "required": ["x", "y", "w", "h"],
                        "additionalProperties": False,
                        "description": "该投注行的局部截图坐标；正常项也要尽量填写，确实无法定位时才为null",
                    },
                },
                "required": [
                    "raw_text",
                    "play_type",
                    "standardized",
                    "amount",
                    "needs_review",
                    "review_reason",
                    "crop_hint",
                ],
                "additionalProperties": False,
            },
        },
        "image_level_notes": {
            "type": "string",
            "description": "图片级备注；没有则为空字符串",
        },
    },
    "required": ["image_file", "items", "image_level_notes"],
    "additionalProperties": False,
}
