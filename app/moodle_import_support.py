from __future__ import annotations


FLW_LANGUAGE_ROOTS = [
    {
        "code": "01-adventure",
        "label": "Adventure",
        "worldCode": "AEW",
        "markers": ("01-adventure", "adventure", "aew", "aew2"),
    },
    {
        "code": "02-real",
        "label": "Real",
        "worldCode": "REW",
        "markers": ("02-real", "real", "rew", "rew2"),
    },
    {
        "code": "03-russian",
        "label": "Russian",
        "worldCode": "RUW",
        "markers": ("03-russian", "russian", "ruw", "ruw2"),
    },
    {
        "code": "04-chinese",
        "label": "Chinese",
        "worldCode": "CHW",
        "markers": ("04-chinese", "chinese", "cw", "chw", "chw2"),
    },
    {
        "code": "05-german",
        "label": "German",
        "worldCode": "GEW",
        "markers": ("05-german", "german", "gw", "gew", "gew2", "gw3"),
    },
    {
        "code": "06-japanese",
        "label": "Japanese",
        "worldCode": "JPW",
        "markers": ("06-japanese", "japanese", "jw", "jpw", "jpw2", "jw3"),
    },
    {
        "code": "07-spanish",
        "label": "Spanish",
        "worldCode": "SW",
        "markers": ("07-spanish", "spanish", "sw", "spw", "espanol", "español"),
    },
    {
        "code": "08-french",
        "label": "French",
        "worldCode": "FW",
        "markers": ("08-french", "french", "fw", "fw_u"),
    },
]


BATCH_TERMINAL_STATUSES = {"complete", "completed_with_issues", "failed", "canceled", "interrupted"}
