import argparse
import asyncio
import datetime
import json
import os

import aiohttp

from utils import Semester
from collectors import DigmiCourseScheduleCollector, ShnatonSyllabusCollector, \
    ShnatonExamCollector, \
    ShantonGeneralInfoCollector

COURSE_FILE_TEMPLATE = '{course}_{year}_{semester}.txt'


async def download_single_course_json(session: aiohttp.ClientSession, course: str, semester: Semester, year: int,
                                      file_path: str):
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

    output_dict = dict(general=general, schedule=schedule_results)
    with open(file_path, 'w') as f:
        json.dump(output_dict, f, ensure_ascii=False)


async def download_courses(courses, semester: Semester, year: int, output_dir: str):
    """
    Download multiple courses from a specific year and semester.
    :param output_dir: If specified, saves the course data to a file path.
    """
    tasks = []

    async with aiohttp.ClientSession() as session:
        for course in courses:
            file_name = COURSE_FILE_TEMPLATE.format(course=course, year=year, semester=int(semester))
            file_path = os.path.join(output_dir, file_name)

            tasks.append(
                download_single_course_json(session, course, semester, year, file_path=file_path)
            )

        await asyncio.gather(*tasks)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--courses', nargs='+', required=True)
    parser.add_argument('-s', '--semester', required=True, type=Semester.from_string)
    parser.add_argument('-y', '--year', type=int, required=False, default=datetime.datetime.now().year)
    parser.add_argument('-d', '--directory', type=str, required=True)
    args = parser.parse_args()

    asyncio.run(download_courses(courses=args.courses, semester=args.semester, year=args.year,
                                 output_dir=args.directory))


if __name__ == '__main__':
    # This is to stop a RuntimeError when exiting the program on Windows.
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    main()
