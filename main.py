import argparse
import asyncio
import datetime
import json
import logging
import os
import time
from urllib.parse import urljoin

import aiohttp as aiohttp
import requests
from mitmproxy.options import Options
from mitmproxy.tools.dump import DumpMaster
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.remote.command import Command as SeleniumCommand
from webdriver_manager.chrome import ChromeDriverManager
from selenium import webdriver

from collectors import DigmiCourseScheduleCollector, ShnatonSyllabusCollector, ShnatonExamCollector, \
    ShantonGeneralInfoCollector
from proxy import ReplaceCoursesJson
from utils import Semester


COURSE_FILE_TEMPLATE = '{course}_{year}_{semester}.txt'
DOWNLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'downloaded_courses')
CHROME_PROFILE_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chrome_profile')
PROXY_PORT = 8080
CHEESEFORK_URL = 'https://cheesefork.cf/'


async def download_single_course_json(session: aiohttp.ClientSession, course: str, semester: Semester, year: int):
    schedule_results = await DigmiCourseScheduleCollector(course=course, year=year, semester=semester,
                                                          async_session=session).acollect()
    naz, faculty, in_charge_person, course_name = await ShnatonSyllabusCollector(course=course, year=year,
                                                                                 async_session=session).acollect()
    exams = await ShnatonExamCollector(course=course, year=year, semester=semester, async_session=session).acollect()
    if course_name is None or faculty is None:
        faculty, course_name, _ = await ShantonGeneralInfoCollector(course=course, year=year,
                                                                    async_session=session).acollect()

    general = {
        'אחראים': in_charge_person,
        "הערות": "",
        "הרצאה": "2",
        "מספר מקצוע": course,
        "מעבדה": "0",
        "מקצועות ללא זיכוי נוסף": "",
        "מקצועות קדם": "",
        "נקודות": str(naz),
        "סילבוס": "",
        "סמינר/פרויקט": "0",
        "פקולטה": faculty,
        "שם מקצוע": course_name,
        "תרגיל": "2"
    }
    if exams:
        general['מועד א'] = f"בתאריך {exams['a'].replace('-', '.')} יום ה"
        general['מועד ב'] = f"בתאריך {exams['b'].replace('-', '.')} יום ו"

    file_name = COURSE_FILE_TEMPLATE.format(course=course, year=year, semester=int(semester))
    with open(os.path.join(DOWNLOAD_FOLDER, file_name), 'w') as f:
        json.dump(dict(general=general, schedule=schedule_results), f, ensure_ascii=False)


async def download_courses(courses, semester: Semester, year: int):
    tasks = []
    async with aiohttp.ClientSession() as session:
        for course in courses:
            tasks.append(
                download_single_course_json(session, course, semester, year)
            )

        await asyncio.gather(*tasks)


def build_proxy(replacement_value):
    # Build proxy
    opts = Options(listen_host='127.0.0.1', listen_port=PROXY_PORT)
    proxy = DumpMaster(opts, with_termlog=False, with_dumper=False)
    proxy.addons.add(ReplaceCoursesJson(replacement_value=replacement_value))
    return proxy


def raise_browser(proxy: DumpMaster):
    """
    :param proxy: Uses the proxy object to call a shutdown on browser exit.
    """
    print('Starting Browser')
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument(f'--proxy-server=127.0.0.1:{PROXY_PORT}')
    chrome_options.add_argument(f"user-data-dir={CHROME_PROFILE_FOLDER}")
    chrome_options.add_argument('--ignore-ssl-errors=yes')
    chrome_options.add_argument('--ignore-certificate-errors')
    service = Service(ChromeDriverManager(log_level=logging.ERROR, print_first_line=False).install())
    chrome = webdriver.Chrome(service=service, options=chrome_options)

    # TODO: This is ugly but whatever
    window_handle_method, window_handle_path_template = chrome.command_executor._commands[
        SeleniumCommand.W3C_GET_CURRENT_WINDOW_HANDLE]  # type: str, str
    session_id = chrome.session_id
    window_handle_path = window_handle_path_template.replace('$sessionId', session_id)
    window_handle_url = urljoin(chrome.command_executor._url, window_handle_path)

    def _is_browser_open():
        try:
            requests.request(window_handle_method, window_handle_url, timeout=1)
            return True
        except Exception:
            return False

    chrome.get(CHEESEFORK_URL)

    while _is_browser_open():
        time.sleep(1)

    print('Chrome quit. Closing app (this may take a bit).')
    chrome.quit()
    print('Chrome stopped. Shutting down proxy.')
    proxy.shutdown()
    print('Proxy shutdown.')
    return


def raise_proxy_and_browser(replacement_value: str):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    proxy = build_proxy(replacement_value)

    # Make sure browser is raised
    loop.run_in_executor(None, raise_browser, proxy)

    print('Starting Proxy')
    proxy.run()


def create_argument_parser() -> argparse.ArgumentParser:
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('-c', '--courses', nargs='+', required=True)
    arg_parser.add_argument('-s', '--semester', required=True, type=Semester.from_string)
    arg_parser.add_argument('-y', '--year', type=int, required=False, default=datetime.datetime.now().year)
    arg_parser.add_argument('-r', '--recreate-courses', action='store_true', default=False)
    arg_parser.add_argument('-d', '--download-only', action='store_true', default=False)
    return arg_parser


def main():
    parser = create_argument_parser()
    args = parser.parse_args()

    # Get/Create folder of existing courses
    try:
        existing_course_ids = set(os.listdir(DOWNLOAD_FOLDER))
    except FileNotFoundError:
        os.mkdir(DOWNLOAD_FOLDER)
        existing_course_ids = set()

    # Get course IDs to download
    if args.recreate_courses:
        course_ids_to_download = list(args.courses)
    else:
        course_ids_to_download = []
        for course_id in args.courses:
            expected_course_file = COURSE_FILE_TEMPLATE.format(course=course_id, year=args.year,
                                                               semester=int(args.semester))
            if expected_course_file in existing_course_ids:
                continue
            course_ids_to_download.append(course_id)

    # Download missing courses
    if course_ids_to_download:
        asyncio.run(
            download_courses(course_ids_to_download, semester=args.semester, year=args.year)
        )

    if args.download_only:
        return

    # Read all courses from files
    course_data = {}
    for course_id in args.courses:
        file_path = os.path.join(DOWNLOAD_FOLDER,
                                 COURSE_FILE_TEMPLATE.format(course=course_id, year=args.year,
                                                             semester=int(args.semester)))
        with open(file_path, 'r') as f:
            course_data[course_id] = json.load(f)

    # Build javascript variable
    js_variable = f'var courses_from_rishum = {json.dumps(list(course_data.values()), ensure_ascii=False)}'

    # Raise selenium/mitmproxy with Cheesefork
    raise_proxy_and_browser(js_variable)


if __name__ == '__main__':
    main()
