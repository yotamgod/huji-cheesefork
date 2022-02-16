function myFunction() {
    // Declare variables
    var input, filter, ul, li, a, i, txtValue;
    input = document.getElementById('myInput');
    filter = input.value.toUpperCase();
    ul = document.getElementById("myUL");
    li = ul.getElementsByTagName('li');

    // Loop through all list items, and hide those who don't match the search query
    for (i = 0; i < li.length; i++) {
        a = li[i].getElementsByTagName("label")[0];
        txtValue = a.textContent || a.innerText;
        if (txtValue.toUpperCase().indexOf(filter) > -1) {
            li[i].style.display = "";
        } else {
            li[i].style.display = "none";
        }
    }
}

function setCookie(cname, cvalue, exdays) {
    const d = new Date();
    d.setTime(d.getTime() + (exdays * 24 * 60 * 60 * 1000));
    let expires = "expires=" + d.toUTCString();
    document.cookie = cname + "=" + cvalue + ";" + expires + ";path=/";
}

function getCookie(cname) {
    let name = cname + "=";
    let decodedCookie = decodeURIComponent(document.cookie);
    let ca = decodedCookie.split(';');
    for (let i = 0; i < ca.length; i++) {
        let c = ca[i];
        while (c.charAt(0) == ' ') {
            c = c.substring(1);
        }
        if (c.indexOf(name) == 0) {
            return c.substring(name.length, c.length);
        }
    }
    return "";
}

let checked_dict = {}

function checkboxChange(id) {
    let checked_elem, unchecked_elem;
    if (id.startsWith('checked')) {
        checked_elem = document.getElementById(id)
        unchecked_elem = document.getElementById('un' + id)
        checked_elem.hidden = true
        let checked_elem_input = checked_elem.getElementsByTagName('input')[0]
        checked_elem_input.checked = false
        delete checked_dict[checked_elem_input.id]
        unchecked_elem.hidden = false
    } else {
        checked_elem = document.getElementById(id.replace('unchecked', 'checked'))
        unchecked_elem = document.getElementById(id)
        checked_elem.hidden = false
        let checked_elem_input = checked_elem.getElementsByTagName('input')[0]
        checked_elem_input.checked = true
        checked_dict[checked_elem_input.id] = ''
        unchecked_elem.hidden = true
    }
    unchecked_elem.getElementsByTagName('input')[0].checked = false
}

function onSubmitFunc(){
    let courses_str = ""
    for (let course in checked_dict) {
        courses_str += course + ','
    }
    setCookie('courses', courses_str.slice(0, -1), 365)
}

function onLoad(){
    let courses_str = getCookie('courses')
    if (courses_str == ''){
        return
    }

    let courses = courses_str.split(',')
    for (let course_idx in courses){
        let li = document.getElementById('unchecked_' + String(courses[course_idx]))
        li.getElementsByTagName('label')[0].click()
    }
    window.scrollTo(0, 0)
}