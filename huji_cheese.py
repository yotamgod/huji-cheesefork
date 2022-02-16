import datetime
import json
import os
from threading import Thread

from flask import Flask, render_template, request, redirect

from cheese_proxied_browser import CheeseProxiedBrowser
from collectors import DigmiAllCoursesCollector
from main import download_courses
from utils import Semester

COURSE_FILE_TEMPLATE = '{course}_{year}_{semester}.txt'
CHEESEFORK_URL = 'https://cheesefork.cf/'
DOWNLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'downloaded_courses')


class HujiCheese:
    """
    A class that controls the flask app and the proxied browser
    """
    def __init__(self):
        self._proxied_browser = CheeseProxiedBrowser(initial_page='http://localhost:5000')
        self._flask_app = Flask(__name__)
        self._add_endpoints()

    def _add_endpoints(self):
        """
        Add endpoints to flask app
        """
        self._flask_app.add_url_rule('/year/<year>', view_func=self.year_index, methods=['GET', 'POST'])
        self._flask_app.add_url_rule('/', view_func=self.index, methods=['GET'])

    async def index(self):
        """
        Main page. Redirects to the year page.
        """
        year = datetime.date.today().year
        return redirect(f'/year/{year}')

    async def year_index(self, year):
        """
        The year page - includes all the courses for a certain year.
        """
        if request.method == 'GET':
            result = await DigmiAllCoursesCollector(year).acollect()
            return render_template("index.html", courses=result)

        semester = Semester.from_string(request.form.get('semester'))
        courses = request.form.getlist('courses')
        should_recreate = True if request.form.get('recreate') else False

        # Get/Create folder of existing courses
        try:
            existing_course_ids = set(os.listdir(DOWNLOAD_FOLDER))
        except FileNotFoundError:
            os.mkdir(DOWNLOAD_FOLDER)
            existing_course_ids = set()

        # Get course IDs to download
        if should_recreate:
            course_ids_to_download = list(courses)
        else:
            course_ids_to_download = []
            for course_id in courses:
                expected_course_file = COURSE_FILE_TEMPLATE.format(course=course_id, year=year,
                                                                   semester=semester)
                if expected_course_file in existing_course_ids:
                    continue
                course_ids_to_download.append(course_id)

        # Download missing courses
        if course_ids_to_download:
            await download_courses(course_ids_to_download, semester=semester, year=year)

        # Read all courses from files
        course_data = {}
        for course_id in courses:
            file_path = os.path.join(DOWNLOAD_FOLDER,
                                     COURSE_FILE_TEMPLATE.format(course=course_id, year=year,
                                                                 semester=int(semester)))
            with open(file_path, 'r') as f:
                course_data[course_id] = json.load(f)

        # Build javascript variable
        js_variable = f'var courses_from_rishum = {json.dumps(list(course_data.values()), ensure_ascii=False)}'

        # Reload the addon that alters the courses in Cheesefork.
        self._proxied_browser.replacement_value = js_variable
        self._proxied_browser.reload_course_replacement()

        return redirect(CHEESEFORK_URL)

    def start(self):
        flask_thread = Thread(target=self._flask_app.run, args=('localhost', 5000), daemon=True)
        flask_thread.start()
        self._proxied_browser.run()


def main():
    hc = HujiCheese()
    hc.start()


if __name__ == '__main__':
    main()
