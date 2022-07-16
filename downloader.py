import argparse
import asyncio
import datetime
import json
import logging
import os
from asyncio import Task
from typing import List

import aiohttp
import tqdm

from utils import Semester
from collectors import DigmiCourseScheduleCollector, ShnatonSyllabusCollector, \
    ShnatonExamCollector, \
    ShantonGeneralInfoCollector, DigmiAllCoursesCollector

COURSE_FILE_TEMPLATE = '{course}_{year}_{semester}.txt'


async def _task_progress_printer(tasks: List[Task]):
    pbar = tqdm.tqdm(total=len(tasks), unit='courses', )
    while True:
        finished_tasks = sum([task.done() for task in tasks])
        pbar.update(finished_tasks - pbar.n)
        if finished_tasks == len(tasks):
            pbar.close()
            return

        await asyncio.sleep(1)


async def download_single_course_json(session: aiohttp.ClientSession, course: str, semester: Semester, year: int,
                                      file_path: str, sem: asyncio.Semaphore):
    """
    Collect Huji info and create a json that matches the Cheesefork format.
    """
    async with sem:
        logging.debug(f'Downloading {course}...')
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
    coros = []
    semaphore = asyncio.Semaphore(10)
    async with aiohttp.ClientSession() as session:
        for course in courses:
            file_name = COURSE_FILE_TEMPLATE.format(course=course, year=year, semester=int(semester))
            file_path = os.path.join(output_dir, file_name)

            coros.append(
                download_single_course_json(session, course, semester, year, file_path=file_path, sem=semaphore)
            )

        tasks = [asyncio.create_task(coro) for coro in coros]

        # Show download task bar if log level is INFO
        if logging.root.level == logging.INFO:
            progress_task = asyncio.create_task(_task_progress_printer(tasks))
            await progress_task

        results = await asyncio.gather(*tasks, return_exceptions=True)
        failed_course_ids = [course_id for result, course_id in zip(results, courses)
                             if isinstance(result, Exception)]

        logging.info(f'Successfully downloaded {len(results) - len(failed_course_ids)} courses.')
        if failed_course_ids:
            logging.error(f'Failed to download {len(failed_course_ids)} courses: {failed_course_ids}')


async def _get_all_course_ids(year):
    result = await DigmiAllCoursesCollector(year).acollect()
    return [course['id'] for course in result]


def main():
    parser = argparse.ArgumentParser()
    courses = parser.add_mutually_exclusive_group(required=True)
    courses.add_argument('-c', '--courses', nargs='+')
    courses.add_argument('-a', '--all-courses', action='store_true')
    courses.add_argument('-f', '--course_file')
    parser.add_argument('-s', '--semester', required=True, type=Semester.from_string)
    parser.add_argument('-y', '--year', type=int, required=False, default=datetime.datetime.now().year)
    parser.add_argument('-d', '--directory', type=str, required=True)
    parser.add_argument('-v', '--verbose', action='store_true')
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO)

    if args.all_courses:
        courses = asyncio.run(_get_all_course_ids(args.year))
    elif args.course_file:
        with open(args.course_file, 'r') as f:
            courses = f.read().splitlines()
    else:
        courses = args.courses

    logging.info(f'Downloading {len(courses)} courses data.')
    asyncio.run(download_courses(courses=courses, semester=args.semester, year=args.year,
                                 output_dir=args.directory))


if __name__ == '__main__':
    # This is to stop a RuntimeError when exiting the program on Windows.
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    main()
