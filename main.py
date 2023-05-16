import logging
import os
import re
import time

import requests
from bs4 import BeautifulSoup as bs4
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler

load_dotenv()

SURNAME=os.getenv('SURNAME')
POLICY=os.getenv('POLICY')
STOMATOLOGY=os.getenv('STOMATOLOGY')
SPECIALITY=os.getenv('SPECIALITY')


class Check():
    def auth (__self__, login_res):
        login_html = bs4(login_res.text, "lxml")
        if login_html.find('div', {'class': 'info-div active'}) is None:
            raise ValueError("Неправильная фамилия или имя полиса. Попробуйте еще раз.")

    def table (__self__, table):
        if table is None:
            raise ValueError("Ошибка при открытии таблицы для записи. Возможно проблема в cookies и неправильной авторизации.")

check = Check()


def login(r):
    login_url = "https://ekb.registratura96.ru/site/login"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    login_data = (
        f"LoginForm[username]={SURNAME}&LoginForm[policy]={POLICY}&submit=Продолжить".encode("utf8"))
    auth_result = r.post(url=login_url, headers=headers, data=login_data)
    check.auth(auth_result)



def dentist(r):
    dentist_url = "https://ekb.registratura96.ru/site/stomatologies"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    dentist_data = (
        f"StomatologyForm[stomatology]={STOMATOLOGY}&SpecialityForm[speciality]={SPECIALITY}"
    ).encode("utf8")

    res = r.post(url=dentist_url, data=dentist_data, headers=headers, cookies=r.cookies)
    res.encoding = "utf-8"

    html = bs4(res.text, "lxml")
    table = html.find('table', {'class': 'items'})
    check.table(table)

    return table


def watcher(t):

    def get_data(t):
        cols = t.findAll("th")
        dates = [c.text[:5] for c in cols][2:]

        rows = t.findAll("tr")

        def remove_tags(str):
            return re.sub(r"\<[^>]*\>", "", str)
        
        def tickets(tickets_html):
            def amount(t):
                return remove_tags(str(t)) if len(remove_tags(str(t))) > 0 else "0"

            def time(t):
                cur_amount = int(amount(t))
                tag_name = "a" if cur_amount > 0 else "div"

                return (
                    bs4(str(t), "html.parser").find(tag_name).attrs["title"]
                    if len(bs4(str(t), "html.parser").text) > 0
                    else None
                )
            
            return [[amount(t), time(t)] for t in tickets_html]
        
        doctors_html = [
            [
                row.find("span", {"class": "font-12pt"}),
                row.findAll("td", {"class": ["clickable ticket", "empty-day ticket"]}),]
            for row in rows
        ]
        doctors = [[remove_tags(str(d[0])), tickets(d[1])] for d in doctors_html][1:]

        return (dates, doctors)
    
    def get_vacant(data):
        vacant = {}
        for d in data[1]:
            for i_x, x in enumerate(d[1]):
                if (int(x[0]) > 0):
                    try:
                        vacant[d[0]].append([data[0][i_x], x[0], x[1]])
                    except KeyError:
                        vacant[d[0]] = [[data[0][i_x],x[0], x[1]]]

        return vacant
    
    data = get_data(t)
    vacant = get_vacant(data)
    return vacant


def request():
    with requests.Session() as r:
        login(r)

        table = dentist(r)
        print(watcher(table))
        return watcher(table)


TOKEN = os.getenv("TOKEN")
UPD_TIME = int(os.getenv("UPD_TIME")) 

def bot(req) -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
    )
    logging.getLogger(__name__)
    async def start(update: Update, context):
        user = update.effective_user
        start_msg = rf"Привет, {user.mention_html()}! Этот бот представляет из себя watcher для сайта записи ко врачу в Екатеринбурге через муниципальный портал. Вводя свои фамилию и номер медицинского полиса, Вы имеете возможность подписаться на интересующих Вас специалистов. Когда появятся свободные окна для записи, этот бот непременно Вас уведомит об этом!"

        await update.message.reply_html(start_msg)
    async def check(update: Update, context):
        def vacant_info(v):
            return f"{v[1]} свободных мест на {v[0]} в промежутке времени {v[2]}"
        cache_msg = ""
        while True:
            data = req()
            is_keys = False
            check_msg = "Текущие свободные записи:"
            for key in data:
                is_keys = True
                check_msg += "\n\n %s: \n • %s" % (
                    key.upper().strip(),
                    ";\n • ".join([vacant_info(x) for x in data[key]]) + ".",
                )
            if (check_msg != cache_msg) and (is_keys == True):
                cache_msg = check_msg
                await update.message.reply_html(check_msg)
            if((is_keys == False) and (len(cache_msg) > 0)):
                cache_msg = ""
                await update.message.reply_html("Больше не осталось мест для записи.")
            time.sleep(UPD_TIME)
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("check", check))
    application.run_polling()



if __name__ == '__main__':
    bot(request)