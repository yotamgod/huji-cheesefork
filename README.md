**WORK IN PROGRESS, USE AT YOUR OWN RISK**

Setup:
pip3 install -r requirements.txt

**Example usage**:

`python main.py -y 2022 -s b -c 80135 80131 67109 69166 72155 76563 80031 80035`

This:
* Downloads all the course info for
  * Year: 2022
  * Semester: b
  * Courses: 80135, 80131, 67109, 69166, 72155, 76563, 80031, 80035
* Opens a browser with the cheesefork of these specific courses.
* Use '-r' flag to refresh (re-download) all course data again (could take some time or fail when Digmi/Huji are offline).