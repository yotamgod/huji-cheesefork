import asyncio
import json
import os

import aiohttp

from utils import Semester
from collectors import DigmiCourseScheduleCollector, ShnatonSyllabusCollector, \
    ShnatonExamCollector, \
    ShantonGeneralInfoCollector

COURSE_FILE_TEMPLATE = '{course}_{year}_{semester}.txt'
DOWNLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'downloaded_courses')


async def download_single_course_json(session: aiohttp.ClientSession, course: str, semester: Semester, year: int):
    """
    Collect Huji info and create a json that matches the Cheesefork format.
    """
    schedule_results = await DigmiCourseScheduleCollector(course=course,
                                                          year=year,
                                                          semester=semester,
                                                          async_session=session).acollect()
    naz, faculty, in_charge_person, course_name = await ShnatonSyllabusCollector(course=course,
                                                                                 year=year,
                                                                                 async_session=session).acollect()
    exams = await ShnatonExamCollector(course=course, year=year, semester=semester,
                                       async_session=session).acollect()
    if course_name is None or faculty is None:
        faculty, course_name, _ = await ShantonGeneralInfoCollector(course=course,
                                                                    year=year,
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
        if 'a' in exams:
            general['מועד א'] = f"בתאריך {exams['a'].replace('-', '.')} יום ה"
        if 'b' in exams:
            general['מועד ב'] = f"בתאריך {exams['b'].replace('-', '.')} יום ו"

    file_name = COURSE_FILE_TEMPLATE.format(course=course, year=year, semester=int(semester))
    with open(os.path.join(DOWNLOAD_FOLDER, file_name), 'w') as f:
        json.dump(dict(general=general, schedule=schedule_results), f, ensure_ascii=False)


async def download_courses(courses, semester: Semester, year: int):
    """
    Download multiple courses from a specific year and semester.
    """
    tasks = []
    async with aiohttp.ClientSession() as session:
        for course in courses:
            tasks.append(
                download_single_course_json(session, course, semester, year)
            )

        await asyncio.gather(*tasks)
