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

DEFAULT_PROXY_PORT = 8080
DEFAULT_PROXY_HOST = '127.0.0.1'
CHROME_PROFILE_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chrome_profile')


class ReplaceCoursesJson:
    """
    Mitmproxy addon to replace the courses json Cheesefork receives
    """
    name = 'course_replacer'

    def __init__(self, replacement_value: str, domain: str = None):
        """
        :param replacement_value: the value to insert instead of the original
        :param domain: the domain (example.com) to make the courses replacement
        """
        self._replacement_value = replacement_value
        self._domain = domain

    def response(self, flow: HTTPFlow):
        if self._domain is not None and flow.request.host != self._domain:
            return

        if 'courses_' in flow.request.url and self._replacement_value:
            try:
                flow.response.text = self._replacement_value
            except Exception:
                logging.exception('Something happened when replacing course json.')


class CheeseProxiedBrowser:
    def __init__(self, proxy_host=DEFAULT_PROXY_HOST, proxy_port=DEFAULT_PROXY_PORT, replacement_value: str = None,
                 initial_page: str = None, replacement_domain: str = None):
        # Proxy
        self._proxy_host = proxy_host
        self._proxy_port = proxy_port
        self._opts: Optional[Options] = None
        self._proxy: Optional[DumpMaster] = None
        self.replacement_value = replacement_value
        self.replacement_domain = replacement_domain

        # Browser
        self._browser: Optional[webdriver.Chrome] = None
        self._initial_page = initial_page

    def activate_course_replacement(self):
        """
        Loads the course replacement json (if it isn't already loaded).
        """
        if self._proxy.addons.get(ReplaceCoursesJson.name):
            # Already activated, so do nothing
            return

        self._proxy.addons.add(ReplaceCoursesJson(self.replacement_value, self.replacement_domain))

    def deactivate_course_replacement(self):
        """
        Removes the course replacement json (if it exists).
        """
        replacer_addon = self._proxy.addons.get(ReplaceCoursesJson.name)
        if not replacer_addon:
            # Addon not there so do nothing
            return

        self._proxy.addons.remove(replacer_addon)

    def reload_course_replacement(self):
        self.deactivate_course_replacement()
        self.activate_course_replacement()

    def _raise_browser(self):
        """
        Raises a browser behind the mitmproxy server (downloading the chrome webdriver if needed).
        Also gets the initial page if specified.
        """
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument(f'--proxy-server=127.0.0.1:{DEFAULT_PROXY_PORT}')
        chrome_options.add_argument(f"user-data-dir={CHROME_PROFILE_FOLDER}")
        chrome_options.add_argument('--ignore-ssl-errors=yes')
        chrome_options.add_argument('--ignore-certificate-errors')
        service = Service(ChromeDriverManager().install())
        self._browser = webdriver.Chrome(service=service, options=chrome_options)
        if self._initial_page is not None:
            self._browser.get(self._initial_page)

    def get_page(self, page: str):
        """
        Makes the selenium controlled browser "get" a page.
        """
        assert self._browser is not None, 'Browser must be run first.'
        self._browser.get(page)

    async def _browser_poller(self):
        """
        Polls to see if the browser is still open (or was close by the user).
        If it is closed, kill the remaining chromedriver.exe process and the proxy as well.
        """

        assert self._browser, 'Browser must be run first.'

        # Send the browser a "keepalive" every second.
        # If the request hangs, it means the browser is probably closed.
        async with aiohttp.ClientSession() as session:

            # Collect window handle url to send keepalives to
            window_handle_method, window_handle_path_template = self._browser.command_executor._commands[
                SeleniumCommand.W3C_GET_CURRENT_WINDOW_HANDLE]  # type: str, str
            session_id = self._browser.session_id
            window_handle_path = window_handle_path_template.replace('$sessionId', session_id)
            window_handle_url = urljoin(self._browser.command_executor._url, window_handle_path)

            # Sub method to poll the browser.
            async def _is_browser_open():
                try:
                    await session.request(window_handle_method, window_handle_url, timeout=1)
                    return True
                except Exception:
                    return False

            while await _is_browser_open():
                await asyncio.sleep(1)

        print('Chrome quit. Closing app.')
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
