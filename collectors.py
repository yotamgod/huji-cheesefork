import json.decoder
from typing import List, Dict, Union, Optional

import aiohttp
from bs4 import BeautifulSoup

from utils import Semester


class HujiDataCollector:
    def __init__(self, method: str, url: str, headers: dict = None, data: dict = None, params: dict = None,
                 async_session: aiohttp.ClientSession = None):
        self.method = method
        self.url = url

        self.data = data or {}
        self.params = params or {}

        headers = headers or {}
        self.headers = {**self._get_default_headers(), **headers}

        self._async_session: Optional[aiohttp.ClientSession] = async_session or aiohttp.ClientSession()

    def _get_default_headers(self) -> dict:
        return {'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                              'Chrome/93.0.4577.63 Safari/537.36'}

    async def acollect(self) -> Union[List, Dict]:
        response = await self._async_session.request(self.method, self.url, data=self.data, params=self.params,
                                                     headers=self.headers)
        return await self._parse_response(response)

    async def _parse_response(self, response: aiohttp.ClientResponse) -> Union[List, Dict]:
        raise NotImplementedError()


class DigmiCourseScheduleCollector(HujiDataCollector):
    DIGMI_URL = 'https://digmi.org/huji/get_course.php'

    def __init__(self, year: int, course: str, semester: Semester, headers: dict = None,
                 async_session: aiohttp.ClientSession = None):
        super().__init__('GET', self.DIGMI_URL, headers, params={'year': year, 'course': course},
                         async_session=async_session)
        self._semester = semester

    async def _parse_response(self, response: aiohttp.ClientResponse) -> Union[List, Dict]:
        lessons = []
        lesson_counter = 10
        type_conversion = {
            'שעור': 'הרצאה',
            'תרג': 'תרגול',
            'מעב': 'מעבדה',
            'שות': 'הרצאה',
            'סדנה': 'תרגול'
        }

        response_text = await response.text()
        response_json = json.loads(response_text, strict=False)
        for lesson in response_json['lessons']:

            lesson_cf_format = {
                'מרצה/מתרגל': lesson['teacher'],
                'קבוצה': lesson['group'],
                'מס.': str(lesson_counter),
                'סוג': type_conversion[lesson['type']]
            }
            for hour in lesson['hours']:
                if (hour['semester'] == 'סמסטר א' and self._semester == Semester.B) \
                        or (hour['semester'] == 'סמסטר ב' and self._semester == Semester.A) \
                        or not hour['hour']:
                    continue

                from_hour, to_hour = hour['hour'].split('-')
                hour_cf_format = {
                    'בניין': f'{hour["place"]}',
                    'חדר': '',
                    'שעה': f'{to_hour} - {from_hour}',
                    'יום': hour['day'].replace('יום ', '').replace("'", '')
                }
                # TODO: Might need to convert hours to 10:3 instead of 10:30
                lessons.append(dict(**lesson_cf_format, **hour_cf_format))
            # pprint.pprint(dict(**lesson_cf_format, **hour_cf_format))
            lesson_counter += 1
        return lessons


class ShantonGeneralInfoCollector(HujiDataCollector):
    SHNATON_URL = 'https://shnaton.huji.ac.il/index.php'

    def __init__(self, year: int, course: str, headers: dict = None, async_session: aiohttp.ClientSession = None):
        data = {
            'peula': 'Simple',
            'maslul': 0,
            'shana': 0,
            'year': year,
            'course': course
        }

        super().__init__('POST', self.SHNATON_URL, headers=headers, data=data, async_session=async_session)

    async def _parse_response(self, response: aiohttp.ClientResponse) -> Union[List, Dict]:
        course_page = BeautifulSoup(await response.text(), features='html5lib')
        faculty_div = course_page.find('div', attrs={'class': 'courseTitle'})
        faculty = faculty_div.text

        course_table = faculty_div.find_next('table')
        english_course_name, hebrew_course_name, course_id = [b.text for b in course_table.find_all('b')]

        course_details_table = course_table.find_next('table')
        test_length, test_type, unknown_field, naz, semesters, _ = [td.text for td in
                                                                    course_details_table.find_all('td')]
        return [faculty, hebrew_course_name, naz]


class ShnatonExamCollector(HujiDataCollector):
    SHNATON_URL = 'https://shnaton.huji.ac.il/index.php'

    def __init__(self, course: str, year: int, semester: Semester, headers: dict = None,
                 async_session: aiohttp.ClientSession = None):
        shanton_exam_request_data = {
            'peula': 'CourseD',
            'course': course,
            'detail': 'examDates',
            'year': year,
            'faculty': 2,
            'maslul': 0
        }
        super().__init__('POST', self.SHNATON_URL, headers, data=shanton_exam_request_data, async_session=async_session)
        self._semester = semester

    async def _parse_response(self, response: aiohttp.ClientResponse) -> Union[List, Dict]:
        exam_page = BeautifulSoup(await response.text(), features='html5lib')

        exam_table = exam_page.find('table').find('table').find('tbody')
        exams = {}
        for tr in exam_table.find_all('tr')[4:]:
            exam_date, exam_hour, exam_notes, location, moed, semester = [td.text for td in tr.find_all('td')]

            if semester == 'סמסטר א' and self._semester == Semester.B \
                    or semester == 'סמסטר ב' and self._semester == Semester.A:
                continue

            if '3' not in moed:
                continue
            if 'חלקי א' in moed:
                exams['a'] = exam_date.replace('-', '.')

            elif 'חלקי ב' in moed:
                exams['b'] = exam_date.replace('-', '.')

        return exams


class ShnatonSyllabusCollector(HujiDataCollector):
    SYLLABUS_URL_TEMPLATE = 'https://shnaton.huji.ac.il/index.php/NewSyl/{course}/1/{year}/'

    def __init__(self, year: int, course: str, headers: dict = None, async_session: aiohttp.ClientSession = None):
        super().__init__('GET', self.SYLLABUS_URL_TEMPLATE.format(year=year, course=course), headers=headers,
                         async_session=async_session)

    async def _parse_response(self, response: aiohttp.ClientResponse) -> Union[List, Dict]:
        soup = BeautifulSoup(await response.text(), features='html5lib')
        if 'אין סילבוס' in soup.text:
            return ['0', None, '', None]
        divs = soup.find_all('div')
        shnaton_fields = {div.contents[1].text: div.contents[-1].strip('\n') for div in divs}
        naz = shnaton_fields['נקודות זכות באוניברסיטה העברית: ']
        faculty = shnaton_fields['היחידה האקדמית שאחראית על הקורס:  ']
        in_charge_person = shnaton_fields['מורה אחראי על הקורס (רכז): ']
        course_name = soup.find('span', attrs={'class': 'h1Syl'}).text.strip().split(' - ')[0]
        return [naz, faculty, in_charge_person, course_name]