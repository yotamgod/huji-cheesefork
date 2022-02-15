import asyncio
import logging
import os
from typing import Optional
from urllib.parse import urljoin

import aiohttp
from mitmproxy.http import HTTPFlow
from mitmproxy.options import Options
from mitmproxy.tools.dump import DumpMaster
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.remote.command import Command as SeleniumCommand

PROXY_PORT = 8080
COURSE_FILE_TEMPLATE = '{course}_{year}_{semester}.txt'
DOWNLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'downloaded_courses')
CHROME_PROFILE_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chrome_profile')
CHEESEFORK_URL = 'https://cheesefork.cf/'


class ReplaceCoursesJson:
    """
    Addon to replace the courses json cheesefork receives
    """
    name = 'course_replacer'

    def __init__(self, replacement_value: str):
        self._replacement_value = replacement_value

    def response(self, flow: HTTPFlow):
        if 'courses_' in flow.request.url and self._replacement_value:
            try:
                flow.response.text = self._replacement_value
            except Exception:
                logging.exception('Something happened')


class CheeseProxiedBrowser:
    def __init__(self, host='127.0.0.1', port=PROXY_PORT, replacement_value=None, initial_page=None):
        self._proxy_host = host
        self._proxy_port = port
        self._opts = None
        self._proxy: Optional[DumpMaster] = None
        self.replacement_value = replacement_value

        self._browser: Optional[webdriver.Chrome] = None
        self._initial_page = initial_page

    def activate_course_replacement(self):
        if self._proxy.addons.get(ReplaceCoursesJson.name):
            # Already activated, so do nothing
            return

        self._proxy.addons.add(ReplaceCoursesJson(self.replacement_value))

    def deactivate_course_replacement(self):
        replacer_addon = self._proxy.addons.get(ReplaceCoursesJson.name)
        if not replacer_addon:
            # Addon not there so do nothing
            return

        self._proxy.addons.remove(replacer_addon)

    def reload_course_replacement(self):
        self.deactivate_course_replacement()
        self.activate_course_replacement()

    def _raise_browser(self):
        print('Starting Browser')
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument(f'--proxy-server=127.0.0.1:{PROXY_PORT}')
        chrome_options.add_argument(f"user-data-dir={CHROME_PROFILE_FOLDER}")
        chrome_options.add_argument('--ignore-ssl-errors=yes')
        chrome_options.add_argument('--ignore-certificate-errors')
        service = Service(ChromeDriverManager(log_level=logging.ERROR, print_first_line=False).install())
        self._browser = webdriver.Chrome(service=service, options=chrome_options)
        if self._initial_page is not None:
            self._browser.get(self._initial_page)

    def get_page(self, page: str):
        assert self._browser is not None, 'Browser must be run first.'
        self._browser.get(page)

    async def _browser_poller(self):
        assert self._browser, 'Browser must be run first.'
        async with aiohttp.ClientSession() as session:
            window_handle_method, window_handle_path_template = self._browser.command_executor._commands[
                SeleniumCommand.W3C_GET_CURRENT_WINDOW_HANDLE]  # type: str, str
            session_id = self._browser.session_id
            window_handle_path = window_handle_path_template.replace('$sessionId', session_id)
            window_handle_url = urljoin(self._browser.command_executor._url, window_handle_path)

            async def _is_browser_open():
                try:
                    await session.request(window_handle_method, window_handle_url, timeout=1)
                    return True
                except Exception:
                    return False

            while await _is_browser_open():
                await asyncio.sleep(1)

        print('Chrome quit. Closing app (this may take a bit).')
        self._browser.service.process.kill()
        self._proxy.shutdown()

    def run(self):
        # Build proxy
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._opts = Options(listen_host=self._proxy_host, listen_port=self._proxy_port)
        self._proxy = DumpMaster(self._opts, with_termlog=False, with_dumper=False)

        # Make sure browser is raised
        print('Starting Browser')
        self._raise_browser()

        # Start a poller for the browser - when it closes, the app will exit
        loop.create_task(self._browser_poller())

        print('Starting Proxy')
        self._proxy.run()

    def stop(self):
        """
        Shuts down the proxy and quits Chrome.
        If Chrome has already been exited, this could take a while.
        """
        self._browser.quit()
        self._proxy.shutdown()
