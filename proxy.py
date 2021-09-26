import logging

from mitmproxy.http import HTTPFlow


class ReplaceCoursesJson:

    def __init__(self, replacement_value: str):
        self._replacement_value = replacement_value

    def response(self, flow: HTTPFlow):
        if 'courses_' in flow.request.url and self._replacement_value:
            try:
                flow.response.text = self._replacement_value
            except Exception:
                logging.exception('Something happened')
