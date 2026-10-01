import logging

from pipeline import config

_configured = False

###

def get_logger(name: str) -> logging.Logger:
    global _configured
    if not _configured:
        config.LOG_DIR.mkdir(parents=True, exist_ok=True)

        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        )

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        file_handler = logging.FileHandler(
            config.LOG_DIR / "pipeline.log", encoding="utf-8"
        )
        file_handler.setFormatter(formatter)

        root = logging.getLogger()
        root.setLevel(config.LOG_LEVEL)
        root.addHandler(console_handler)
        root.addHandler(file_handler)

        _configured = True

    return logging.getLogger(name)

###