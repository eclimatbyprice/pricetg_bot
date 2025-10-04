
import os, json, math, logging
from fastapi import FastAPI, Request, HTTPException
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("calc-bot")

# === ENV ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "secret123")
EXTERNAL_URL = os.getenv("EXTERNAL_URL")  # set after first deploy

if not BOT_TOKEN:
    raise RuntimeError("Set BOT_TOKEN env var")

# === load pricing ===
DEFAULT_PR = {
  "cities":{"Минск":{"coeff":1.0,"travel_km_price":1.2,"free_zone_km":15},
            "Орша":{"coeff":0.92,"travel_km_price":0.9,"free_zone_km":10},
            "Брест":{"coeff":0.95,"travel_km_price":1.0,"free_zone_km":15}},
  "base":{"монтаж_сплит_до_3_кВт":240,"монтаж_сплит_3_5_кВт":270,"монтаж_сплит_5_кВт":320,
          "трасса_сверх_включенных_м_за_м":14,"сверление_бетон":35,"сверление_кирпич":25},
  "included":{"трасса_включено_м":3},
  "coeffs":{"высота_до_3м":1.0,"высота_3_5м":1.15,"высота_5_8м":1.35,"срочность_обычно":1.0,"срочность_сегодня":1.2},
  "discounts":{"2_и_более_внутренних_блока":0.95}
}

PR_PATH = os.getenv("PRICING_PATH", "pricing.json")
if os.path.exists(PR_PATH):
    try:
        with open(PR_PATH, "r", encoding="utf-8") as f:
            PR = json.load(f)
    except Exception:
        PR = DEFAULT_PR
else:
    PR = DEFAULT_PR

# === Bot ===
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

CITIES = list(PR["cities"].keys())
WORKS = [k for k in PR["base"].keys() if k.startswith("монтаж_сплит")]
HEIGHTS = {"до 3 м":"высота_до_3м","3–5 м":"высота_3_5м","5–8 м":"высота_5_8м"}
URGENCY = {"обычно":"срочность_обычно","сегодня":"срочность_сегодня"}

def kb(opts):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=o)] for o in opts],
        resize_keyboard=True
    )

def money(x): return f"{math.ceil(x)} BYN"

def calc_quote(city, work, qty, length, drilling, height_label, urgency_label, km_out):
    base = PR["base"][work]*qty
    incl_m = PR["included"]["трасса_включено_м"]*qty
    extra_m = max(0.0, length - incl_m)
    extra_cost = extra_m * PR["base"]["трасса_сверх_включенных_м_за_м"]
    drill_cost = 0
    if drilling=="бетон": drill_cost = PR["base"]["сверление_бетон"]
    elif drilling=="кирпич": drill_cost = PR["base"]["сверление_кирпич"]
    height_coeff = PR["coeffs"][HEIGHTS[height_label]]
    urgency_coeff = PR["coeffs"][URGENCY[urgency_label]]
    city_coeff = PR["cities"][city]["coeff"]
    free_zone = PR["cities"][city]["free_zone_km"]
    km_price = PR["cities"][city]["travel_km_price"]
    travel = max(0.0, km_out - free_zone)*km_price

    subtotal = (base*height_coeff) + extra_cost + drill_cost
    subtotal *= city_coeff * urgency_coeff
    disc = PR["discounts"]["2_и_более_внутренних_блока"] if qty>=2 else 1.0
    total = subtotal*disc + travel

    parts = [
      f"Город: <b>{city}</b> (коэф {city_coeff})",
      f"Работа: <b>{work}</b> × {qty} = {money(base)}",
      f"Трасса: {length} м (вкл. {incl_m} м), доп {extra_m:.1f} м = {money(extra_cost)}",
      f"Сверление: {drilling} = {money(drill_cost)}",
      f"Высота: {height_label}, Срочность: {urgency_label}",
      f"Промежуточно: {money(subtotal)}",
      f"Скидка за ≥2 блока: {'есть' if qty>=2 else 'нет'}",
      f"Выезд: {money(travel) if travel>0 else '0 BYN'}",
      f"<b>ИТОГО: {money(total)}</b>"
    ]
    return "\n".join(parts), total

class Calc(StatesGroup):
    city = State(); work = State(); qty = State(); length = State()
    drilling = State(); height = State(); urgency = State(); km_outside = State()

@dp.message(CommandStart())
async def start(m: types.Message, state: FSMContext):
    await state.clear()
    await m.answer("Привет! Я калькулятор стоимости работ.\nВыберите город:", reply_markup=kb(CITIES))
    await state.set_state(Calc.city)

@dp.message(Calc.city)
async def h_city(m: types.Message, state: FSMContext):
    if m.text not in CITIES: return await m.answer("Выберите из списка.")
    await state.update_data(city=m.text)
    await m.answer("Тип монтажа:", reply_markup=kb(WORKS))
    await state.set_state(Calc.work)

@dp.message(Calc.work)
async def h_work(m: types.Message, state: FSMContext):
    if m.text not in WORKS: return await m.answer("Выберите из списка.")
    await state.update_data(work=m.text)
    await m.answer("Сколько внутренних блоков? (число)", reply_markup=kb(["1","2","3","4"]))
    await state.set_state(Calc.qty)

@dp.message(Calc.qty)
async def h_qty(m: types.Message, state: FSMContext):
    if not m.text.isdigit(): return await m.answer("Укажи число.")
    await state.update_data(qty=int(m.text))
    incl = PR["included"]["трасса_включено_м"]
    await m.answer(f"Длина трассы (м)? (в тариф включено {incl} м)", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(Calc.length)

@dp.message(Calc.length)
async def h_len(m: types.Message, state: FSMContext):
    try: length = float(m.text.replace(",","."))
    except: return await m.answer("Например: 6 или 7.5")
    await state.update_data(length=length)
    await m.answer("Сверление? (бетон/кирпич/нет)", reply_markup=kb(["бетон","кирпич","нет"]))
    await state.set_state(Calc.drilling)

@dp.message(Calc.drilling)
async def h_drill(m: types.Message, state: FSMContext):
    if m.text not in ["бетон","кирпич","нет"]: return await m.answer("Выбери бетон/кирпич/нет")
    await state.update_data(drilling=m.text)
    await m.answer("Высота работ:", reply_markup=kb(list(HEIGHTS.keys())))
    await state.set_state(Calc.height)

@dp.message(Calc.height)
async def h_height(m: types.Message, state: FSMContext):
    if m.text not in HEIGHTS: return await m.answer("Выберите из списка.")
    await state.update_data(height=m.text)
    await m.answer("Срочность:", reply_markup=kb(list(URGENCY.keys())))
    await state.set_state(Calc.urgency)

@dp.message(Calc.urgency)
async def h_urg(m: types.Message, state: FSMContext):
    if m.text not in URGENCY: return await m.answer("Выберите из списка.")
    await state.update_data(urgency=m.text)
    await m.answer("Сколько км за чертой города? (0 если в черте)", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(Calc.km_outside)

@dp.message(Calc.km_outside)
async def h_km(m: types.Message, state: FSMContext):
    try: km = float(m.text.replace(",","."))
    except: return await m.answer("Например: 0 или 12")
    await state.update_data(km_outside=km)
    d = await state.get_data()
    text, total = calc_quote(
        d["city"], d["work"], int(d["qty"]), float(d["length"]),
        d["drilling"], d["height"], d["urgency"], float(d["km_outside"])
    )
    await m.answer(text)
    await state.clear()

# === FASTAPI & WEBHOOK ===
app = FastAPI()

@app.on_event("startup")
async def on_startup():
    await bot.delete_webhook(drop_pending_updates=True)
    if EXTERNAL_URL:
        url = f"{EXTERNAL_URL}/webhook/{WEBHOOK_SECRET}"
        await bot.set_webhook(url=url, drop_pending_updates=True)

@app.post("/webhook/{secret}")
async def tg_webhook(secret: str, request: Request):
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")
    update = types.Update.model_validate(await request.json())
    await dp.feed_update(bot=bot, update=update)
    return {"ok": True}

@app.get("/")
async def health():
    try:
        info = await bot.get_webhook_info()
        return {"status": "ok", "webhook_url": info.url}
    except Exception as e:
        return {"status": "ok", "webhook_url": None, "error": str(e)}
