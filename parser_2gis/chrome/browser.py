from __future__ import annotations

import os
import time
import io
import re
import shutil
import subprocess
import tempfile
from typing import TYPE_CHECKING

from ..common import wait_until_finished
from ..logger import logger
from .exceptions import ChromePathNotFound
from .utils import free_port, locate_chrome_path

if TYPE_CHECKING:
    from .options import ChromeOptions


class ChromeBrowser:
    """Chrome Browser with temporary profile.

    Args:
        chrome_options: Chrome options.
    """

    def __init__(self, chrome_options: ChromeOptions) -> None:
        binary_path = (
            chrome_options.binary_path
            if chrome_options.binary_path
            else locate_chrome_path()
        )

        if not binary_path:
            raise ChromePathNotFound

        logger.debug("Запуск Chrome Браузера.")

        self._patch_chrome_executable(binary_path)

        self._profile_path = tempfile.mkdtemp()
        self._remote_port = free_port()
        self._chrome_cmd = [
            binary_path,
            f"--remote-debugging-port={self._remote_port}",
            f"--user-data-dir={self._profile_path}",
            "--no-default-browser-check",
            "--no-first-run",
            "--no-sandbox",
            "--disable-fre",
            "--remote-allow-origins=*",
            f"--js-flags=--expose-gc --max-old-space-size={chrome_options.memory_limit}",
        ]

        if chrome_options.start_maximized:
            self._chrome_cmd.append("--start-maximized")

        if chrome_options.headless:
            logger.debug("В Chrome установлен в скрытый режим.")
            self._chrome_cmd.append("--headless")
            self._chrome_cmd.append("--disable-gpu")

        if chrome_options.disable_images:
            logger.debug("В Chrome отключены изображения.")
            self._chrome_cmd.append("--blink-settings=imagesEnabled=false")

        self._xvfb_proc = None
        use_xvfb = True
        # if chrome_options.use_xvfb:
        if use_xvfb:
            logger.debug("Запуск Chrome с использованием Xvfb.")
            self._xvfb_proc = subprocess.Popen(
                ["Xvfb", ":99", "-ac"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            os.environ["DISPLAY"] = ":99"

        if chrome_options.silent_browser:
            logger.debug("В Chrome отключен вывод отладочной информации.")
            self._proc = subprocess.Popen(
                self._chrome_cmd,
                shell=False,
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
            )
        else:
            self._proc = subprocess.Popen(self._chrome_cmd, shell=False)

    def _patch_chrome_executable(self, executable_path: str) -> None:
        start = time.perf_counter()
        logger.info(f"Патчинг исполняемого файла Chrome: {executable_path}")

        try:
            with io.open(executable_path, "r+b") as fh:
                content = fh.read()
                match_injected_codeblock = re.search(rb"\{window\.cdc.*?;\}", content)
                if match_injected_codeblock:
                    target_bytes = match_injected_codeblock[0]
                    new_target_bytes = (
                        b'{console.log("undetected chromedriver 1337!")}'.ljust(
                            len(target_bytes), b" "
                        )
                    )
                    new_content = content.replace(target_bytes, new_target_bytes)
                    if new_content == content:
                        logger.warning(
                            "Что-то пошло не так при патчинге бинарного файла Chrome. Не удалось найти блок кода для инъекции."
                        )
                    else:
                        logger.debug(
                            f"Найден блок:\n{target_bytes}\nЗаменяем на:\n{new_target_bytes}"
                        )
                    fh.seek(0)
                    fh.write(new_content)
        except PermissionError:
            logger.error(
                f"Отказано в доступе при попытке патчинга файла Chrome: {executable_path}"
            )
            # raise

        logger.debug(f"Патчинг занял {time.perf_counter() - start:.2f} секунд")

    @property
    def remote_port(self) -> int:
        """Remote debugging port."""
        return self._remote_port

    @wait_until_finished(timeout=5, throw_exception=False)
    def _delete_profile(self) -> bool:
        """Delete profile.

        Returns:
            `True` on successful deletion, `False` on failure.
        """
        shutil.rmtree(self._profile_path, ignore_errors=True)
        profile_deleted = not os.path.isdir(self._profile_path)
        return profile_deleted

    def close(self) -> None:
        """Close browser and delete temporary profile."""
        logger.debug("Завершение работы Chrome Браузера.")

        # Close the browser
        self._proc.terminate()
        self._proc.wait()

        # Close Xvfb if used
        if self._xvfb_proc:
            self._xvfb_proc.terminate()
            self._xvfb_proc.wait()

        # Delete temporary profile
        self._delete_profile()

    def __repr__(self) -> str:
        classname = self.__class__.__name__
        return f"{classname}(arguments={self._chrome_cmd!r})"
