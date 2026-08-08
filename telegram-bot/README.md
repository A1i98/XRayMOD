# ربات تلگرام XRayMOD

ساخت، فهرست، حذف و به‌روزرسانی پنل روی Cloudflare از تلگرام.

## قابلیت‌ها

- ساخت پنل با توکن CF، نام کاربری و رمز (۳ مرحله)
- چند پنل برای هر کاربر تلگرام
- حذف Worker و D1 مربوطه
- آپدیت از `main` گیت‌هاب (`git pull` + rebuild + deploy)
- کیبورد پایین با دکمه‌های فارسی

## دستورها و دکمه‌ها

| دکمه / متن | کار |
|:-----------|:----|
| ساخت پنل جدید | شروع ویزارد ۳ مرحله‌ای |
| پنل‌های من | فهرست + لینک ورود |
| آپدیت همه | آپدیت همه پنل‌ها از GitHub |
| راهنما | راهنمای کوتاه |
| `حذف 1` | حذف پنل با شناسه |
| `آپدیت 1` | آپدیت یک پنل |
| `/start` `/help` `/create` `/cancel` | دستورهای استاندارد |

## نیازمندی‌ها

- Python 3.10+
- Node.js + npm
- git
- دسترسی شبکه به Cloudflare و GitHub

## نصب

```bash
cd telegram-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# BOT_TOKEN را از @BotFather بگذارید
python bot.py
```

متغیرهای اختیاری در `.env`:

| کلید | توضیح |
|:-----|:------|
| `BOT_TOKEN` | توکن ربات (اجباری) |
| `REPO_URL` | پیش‌فرض: فورک askarniroomand/XRayMOD |
| `WORK_ROOT` | مسیر کار (پیش‌فرض `~/.xraymod-bot`) |
| `ALLOW_USER_IDS` | لیست شناسه تلگرام مجاز (خالی = همه) |
