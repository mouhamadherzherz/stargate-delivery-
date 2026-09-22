# 📋 دليل نظام Stargate Delivery System - الدليل الشامل والكامل
### آخر تحديث: 2026-09-16
### الإصدار: 2.0.0-PROD (Enterprise Edition)

---

> [!IMPORTANT]
> **هذا الملف سري للغاية** - يحتوي على جميع كلمات المرور والمفاتيح والروابط.
> لا تشارك هذا الملف مع أي شخص غير مخوّل.

---

## 📁 1. هيكل المشروع (Project Structure)

```
D:\STARGATE\repo\                    ← المجلد الرئيسي للمشروع
│
├── app.py                           ← التطبيق الرئيسي (Flask) - 12,000+ سطر
├── config.py                        ← إعدادات النظام المركزية
├── secure_env.py                    ← إدارة المتغيرات والبيئة الآمنة
├── license_manager.py               ← نظام الترخيص والتفعيل (Offline + Cloud)
├── license_generator_gui.py         ← أداة توليد أكواد التفعيل (Tkinter GUI)
├── node_lock.py                     ← ربط البرنامج بعتاد الجهاز (Hardware Lock)
├── ota_updater.py                   ← نظام التحديث عن بعد (OTA Updates)
├── migration_engine.py              ← محرك ترقية قاعدة البيانات تلقائياً
├── recovery_engine.py               ← أداة استرداد الحسابات
├── stargate_master.py               ← غرفة العمليات المركزية (Blueprint)
├── stargate_security_manager.py     ← إدارة الأمان المتقدمة
├── stargate_ai_engine.py            ← محرك الذكاء الاصطناعي
├── telegram_reporter.py             ← إرسال التقارير عبر تيليجرام
├── backup_lifecycle_manager.py      ← إدارة النسخ الاحتياطي
├── gemini_client.py                 ← الاتصال بـ Google Gemini AI
├── google_drive_backup.py           ← النسخ الاحتياطي على Google Drive
├── run_master.py                    ← تشغيل غرفة العمليات كبرنامج سطح مكتب
├── create_empty_db.py               ← إنشاء قاعدة بيانات فارغة جديدة
│
├── master_config.json               ← إعدادات غرفة العمليات (كلمة السر + Firebase)
├── master_licenses.json             ← سجل التراخيص المولّدة
├── cloud_config.json                ← رابط Firebase للتحكم السحابي
├── RELEASE_MANIFEST.json            ← بيان الإصدار الحالي
│
├── templates/                       ← ملفات HTML (واجهات المستخدم)
│   ├── dashboard.html               ← لوحة التحكم الرئيسية
│   ├── orders.html                  ← إدارة الطلبات
│   ├── merchants.html               ← إدارة التجار
│   ├── customers.html               ← إدارة الزبائن
│   ├── couriers.html                ← إدارة السائقين (لا يوجد ملف مستقل)
│   ├── settlements.html             ← التسويات المالية
│   ├── treasury.html                ← إدارة الخزينة
│   ├── reports.html                 ← التقارير
│   ├── employees.html               ← إدارة الموظفين
│   ├── settings.html                ← الإعدادات العامة
│   ├── products.html                ← إدارة المنتجات
│   ├── login.html                   ← صفحة تسجيل الدخول
│   ├── admin_updates.html           ← صفحة تحديث النظام عند الزبون
│   ├── updates_dashboard.html       ← لوحة التحديثات المركزية (للمالك)
│   ├── sg_master_dashboard.html     ← غرفة العمليات الرئيسية
│   ├── sg_master_login.html         ← تسجيل دخول غرفة العمليات
│   ├── sg_master_customer_edit.html ← إدارة بيانات الزبون (CRM)
│   ├── courier_app.html             ← تطبيق السائق (موبايل)
│   ├── map_dashboard.html           ← خريطة تتبع السائقين
│   ├── system_health.html           ← صحة النظام
│   ├── user_guide.html              ← دليل المستخدم
│   └── ...                          ← (وملفات طباعة وبوليصات أخرى)
│
├── static/                          ← ملفات CSS/JS/صور
│   └── icons/stargate_logo.ico      ← أيقونة البرنامج
│
├── data/                            ← مجلد قواعد البيانات
│   └── stargate_production.db       ← قاعدة البيانات الرئيسية (SQLite WAL)
│
├── StargateDelivery.spec            ← إعدادات بناء EXE (PyInstaller)
├── StarGate_Setup.iss               ← سكريبت بناء ملف التثبيت (Inno Setup)
├── Stargate_Master.spec             ← إعدادات بناء غرفة العمليات EXE
│
├── dist/StargateDelivery/           ← مخرجات PyInstaller (ملفات EXE)
├── installer_output/                ← مخرجات Inno Setup (ملف التثبيت النهائي)
│   └── StargateDelivery_Setup_v2.0.exe  ← ★ ملف التثبيت الجاهز للزبون
│
├── build/                           ← ملفات البناء المؤقتة
├── Update_Package/                  ← حزمة التحديث للموظفين
├── requirements.txt                 ← المكتبات المطلوبة
└── .env.example                     ← مثال على ملف الإعدادات البيئية
```

---

## 🔐 2. جميع كلمات المرور والحسابات

### 2.1 غرفة العمليات المركزية (Master Control Room)
| البند | القيمة |
|-------|--------|
| **الرابط** | `http://localhost:8085/sg_master` |
| **كلمة المرور الافتراضية** | `STARGATE-MASTER-2026` |
| **ملاحظة** | يمكن تغييرها من داخل غرفة العمليات → الإعدادات |
| **ملف الإعدادات** | `master_config.json` |
| **تشغيل كبرنامج سطح مكتب** | عبر `Stargate_Master.exe` أو `python run_master.py` |

### 2.2 حساب المدير (Admin) عند الزبون
| البند | القيمة |
|-------|--------|
| **اسم المستخدم** | `stargate` |
| **كلمة المرور الافتراضية** | `stargate@ChangeMeImmediately2026` |
| **رمز PIN الافتراضي** | `19701313` |
| **ملاحظة** | يتم تغييرها عند أول تسجيل دخول |

### 2.3 حساب الصيانة الفنية (Maintenance)
| البند | القيمة |
|-------|--------|
| **اسم المستخدم** | `maintenance` |
| **كلمة المرور** | `Maint#C4925587` |
| **رمز PIN** | `586953` |
| **الصلاحيات** | فحص النظام، ضغط قاعدة البيانات، النسخ الاحتياطي، إعادة تعيين كلمات المرور |

### 2.4 مفتاح التشفير الأساسي للتراخيص
| البند | القيمة |
|-------|--------|
| **SECRET_KEY_SEED** | `STARGATE_ENTERPRISE_LICENSE_MASTER_KEY_2026_PROD` |
| **الملف** | `license_manager.py` سطر 13 |
| **ملاحظة** | ⚠️ هذا المفتاح يجب أن يكون مطابقاً في أداة التوليد وعند الزبون |

---

## ☁️ 3. الخدمات السحابية والمواقع المرتبطة

### 3.1 Firebase Realtime Database (Cloud Kill Switch)
| البند | القيمة |
|-------|--------|
| **الرابط** | `https://stargate-experts-default-rtdb.firebaseio.com/` |
| **الموقع** | [console.firebase.google.com](https://console.firebase.google.com/) |
| **الاستخدام** | إيقاف/تشغيل تراخيص الزبائن عن بعد |
| **ملف الإعدادات عند الزبون** | `cloud_config.json` |
| **ملف الإعدادات عند المالك** | `master_config.json` → حقل `firebase_url` |
| **كيف يعمل** | عند إلغاء ترخيص من غرفة العمليات، يتم إرسال الكود إلى Firebase تحت `/revoked/CODE`. عند تشغيل البرنامج عند الزبون، يتحقق من Firebase إذا كان الكود ملغى |

### 3.2 Google Gemini AI (اختياري)
| البند | القيمة |
|-------|--------|
| **المتغير** | `GEMINI_API_KEY` في `.env` |
| **الموقع** | [aistudio.google.com](https://aistudio.google.com/) |
| **الاستخدام** | مساعد ذكاء اصطناعي داخل البرنامج |

### 3.3 Telegram Bot (اختياري)
| البند | القيمة |
|-------|--------|
| **المتغير** | `TELEGRAM_BOT_TOKEN` و `TELEGRAM_CHAT_ID` في `.env` |
| **الموقع** | [t.me/BotFather](https://t.me/BotFather) |
| **الاستخدام** | إرسال تقارير يومية وتنبيهات تلقائية |

### 3.4 Google Drive Backup (اختياري)
| البند | القيمة |
|-------|--------|
| **المتغير** | `GDRIVE_SERVICE_ACCOUNT_JSON` و `GDRIVE_FOLDER_ID` |
| **الاستخدام** | نسخ احتياطي تلقائي لقاعدة البيانات على Google Drive |

---

## 🛠️ 4. الأدوات والبرامج المطلوبة على جهاز المطور

### 4.1 البرامج الأساسية (يجب تثبيتها)
| البرنامج | الإصدار | المسار | الاستخدام |
|----------|---------|--------|-----------|
| **Python** | 3.12 | `C:\Users\mouha\AppData\Local\Programs\Python\Python312\` | تشغيل الكود |
| **PyInstaller** | أحدث إصدار | `pip install pyinstaller` | تحويل البرنامج إلى EXE |
| **Inno Setup 7** | 7.x | `C:\Program Files\Inno Setup 7\ISCC.exe` | بناء ملف التثبيت Setup.exe |
| **Git** | أحدث إصدار | عبر PATH | التحكم بالإصدارات |

### 4.2 مكتبات Python المطلوبة
```bash
pip install flask werkzeug waitress cryptography pywebview requests
pip install google-api-python-client google-auth google-auth-httplib2
pip install pyinstaller
```

### 4.3 ملف المتطلبات (requirements.txt)
```
Flask>=3.0.0
Werkzeug>=3.0.0
gunicorn>=21.2.0
google-api-python-client>=2.100.0
google-auth>=2.23.0
google-auth-httplib2>=0.1.1
requests>=2.31.0
```

---

## 🏗️ 5. كيفية بناء النسخة وتوزيعها للزبائن

### 5.1 الخطوة 1: بناء ملفات EXE (PyInstaller)
```powershell
cd D:\STARGATE\repo
python create_empty_db.py
python -m PyInstaller StargateDelivery.spec --clean --noconfirm
```
**النتيجة:** مجلد `dist\StargateDelivery\` يحتوي على كل ملفات البرنامج

### 5.2 الخطوة 2: بناء ملف التثبيت (Inno Setup)
```powershell
& "C:\Program Files\Inno Setup 7\ISCC.exe" StarGate_Setup.iss
```
**النتيجة:** `installer_output\StargateDelivery_Setup_v2.0.exe` ← هذا هو الملف الذي تعطيه للزبون

### 5.3 الخطوة 3: نسخ الملف إلى الفلاشة
```powershell
Copy-Item "D:\STARGATE\repo\installer_output\StargateDelivery_Setup_v2.0.exe" "F:\" -Force
```

### 5.4 بناء غرفة العمليات (Stargate Master) كـ EXE
```powershell
python -m PyInstaller Stargate_Master.spec --clean --noconfirm
```

---

## 🔑 6. نظام التراخيص والتفعيل (كيف يعمل)

### 6.1 عملية التفعيل خطوة بخطوة:
1. الزبون يثبت البرنامج على جهازه
2. يظهر له **رقم الجهاز** (Hardware ID) مثل: `E47E-FCD3`
3. الزبون يرسل رقم الجهاز للمالك
4. المالك يدخل غرفة العمليات → يضغط "توليد كود جديد"
5. يُدخل رقم جهاز الزبون + المدة (مثلاً 365 يوم)
6. يتم توليد كود مثل: `CIP4-MK43-WSB2-H4QG`
7. يرسل الكود للزبون
8. الزبون يُدخل الكود في شاشة التفعيل

### 6.2 أداة توليد الأكواد (بديل):
```powershell
cd D:\STARGATE\repo
python license_generator_gui.py
```
تفتح نافذة GUI يمكن من خلالها توليد الأكواد.

### 6.3 إيقاف ترخيص زبون (Cloud Kill Switch):
1. ادخل غرفة العمليات → جدول الزبائن
2. اضغط "إدارة ⚙️" بجانب الزبون
3. اضغط "تحديد كملغى 🛑"
4. البرنامج يرسل الكود إلى Firebase تلقائياً
5. عند الزبون: في المرة القادمة التي يفتح فيها البرنامج، سيتم منعه

### 6.4 إعادة تنشيط ترخيص:
- اضغط "إعادة التنشيط ✅" من نفس الصفحة
- يتم حذف الكود من Firebase

---

## 🖥️ 7. تشغيل النظام للمطور

### 7.1 تشغيل السيرفر الرئيسي (للتطوير):
```powershell
cd D:\STARGATE\repo
python app.py
```
**البرنامج يعمل على:** `http://localhost:8085`

### 7.2 تشغيل غرفة العمليات كبرنامج سطح مكتب:
```powershell
python run_master.py
```
أو عبر `Stargate_Master.exe` (إذا تم بناؤها)

### 7.3 المنافذ المستخدمة:
| المنفذ | الاستخدام |
|--------|-----------|
| `8085` | السيرفر الرئيسي (app.py) |

---

## 📊 8. قاعدة البيانات

### 8.1 النوع: SQLite مع وضع WAL
- **المسار عند الزبون:** `C:\StargateDelivery\data\stargate_production.db`
- **المسار عند المطور:** `D:\STARGATE\repo\data\stargate_production.db`
- **قاعدة بيانات فارغة:** `D:\STARGATE\repo\data\stargate_empty.db`

### 8.2 الجداول الرئيسية:
| الجدول | الوصف |
|--------|-------|
| `settings` | إعدادات النظام العامة |
| `employees` | الموظفين والحسابات |
| `orders` | الطلبات |
| `merchants` | التجار |
| `customers` | الزبائن |
| `couriers` | السائقين |
| `treasuries` | الخزينة والصناديق |
| `treasury_transactions` | حركات الخزينة |
| `products` | المنتجات |
| `settlements` | التسويات |
| `audit_log` | سجل المراقبة |

---

## 🔄 9. نظام التحديثات (OTA Updates)

### 9.1 كيف يعمل التحديث عند الزبون:
1. الزبون يدخل الإعدادات → "تحديث النظام"
2. يمكنه رفع ملف `.zip` يحتوي على الملفات الجديدة
3. النظام يستخرج الملفات ويستبدل القديمة (بدون لمس قاعدة البيانات)
4. يعيد تشغيل نفسه تلقائياً

### 9.2 كيف تُعد حزمة التحديث:
```powershell
cd D:\STARGATE\repo
.\BUILD_UPDATE_PACKAGE.bat
```
**النتيجة:** مجلد `Update_Package\` جاهز للإرسال

### 9.3 الإصلاح الأخير (مهم!):
في النسخة القديمة، كان نظام التحديث يحاول إعادة تشغيل `pythonw.exe app.py` بعد التحديث، وهذا لا يعمل عند الزبون لأنه لا يملك Python! تم إصلاح هذا ليستخدم `StargateDelivery.exe` تلقائياً.

---

## 📱 10. تطبيق السائق (Courier App)

- **الرابط:** `http://[IP_الخادم]:8085/courier/app`
- يدخل السائق برقم PIN الخاص به
- يمكنه تحديث حالة الطلبات وتأكيد التسليم
- يرسل موقعه GPS تلقائياً

---

## 🗂️ 11. الملفات المهمة للتعديل

### ملفات يجب تعديلها عند التحديث:
| الملف | السبب |
|-------|-------|
| `app.py` | الكود الرئيسي - أي تعديل على الوظائف |
| `templates/*.html` | واجهات المستخدم |
| `static/` | ملفات CSS/JS/صور |
| `ota_updater.py` | إذا تم تغيير آلية التحديث |
| `license_manager.py` | إذا تم تغيير نظام التراخيص |
| `stargate_master.py` | غرفة العمليات المركزية |

### ملفات لا تُرسل للزبون أبداً:
| الملف | السبب |
|-------|-------|
| `license_generator_gui.py` | أداة توليد الأكواد (للمالك فقط) |
| `build_protected.py` | أداة حماية الكود |
| `StargateDelivery.spec` | إعدادات البناء |
| `StarGate_Setup.iss` | سكريبت التثبيت |
| `master_config.json` | إعدادات غرفة العمليات |
| `master_licenses.json` | سجل التراخيص |

---

## 📋 12. التراخيص المولّدة حتى الآن

| الزبون | الهاتف | كود التفعيل | رقم الجهاز | تاريخ الانتهاء | الحالة |
|--------|--------|-------------|------------|----------------|--------|
| stargate delivery | 81153001 | `CIP4-MK43-WSB2-H4QG` | `E47E-FCD3` | 2036-09-13 | ✅ نشط |

---

## 🏢 13. مسار التثبيت عند الزبون

```
C:\StargateDelivery\
├── StargateDelivery.exe          ← الملف الرئيسي (يعمل تلقائياً)
├── _internal\                    ← ملفات Python المُحزمة
│   ├── templates\                ← واجهات HTML
│   ├── static\                   ← CSS/JS
│   ├── data\                     ← قاعدة البيانات الفارغة
│   ├── cloud_config.json         ← رابط Firebase
│   └── ...                       ← باقي المكتبات
├── data\                         ← قاعدة بيانات الزبون (لا تُحذف أبداً!)
│   └── stargate_production.db
└── db_backups\                   ← النسخ الاحتياطية التلقائية
```

---

## ⚡ 14. الأوامر السريعة (Quick Reference)

```powershell
# ═══ تشغيل النظام ═══
cd D:\STARGATE\repo
python app.py                                          # تشغيل السيرفر
python run_master.py                                   # غرفة العمليات

# ═══ بناء نسخة جديدة للزبون ═══
python create_empty_db.py                              # إنشاء قاعدة بيانات فارغة
python -m PyInstaller StargateDelivery.spec --clean --noconfirm    # بناء EXE
& "C:\Program Files\Inno Setup 7\ISCC.exe" StarGate_Setup.iss     # بناء Setup

# ═══ توليد كود تفعيل (من سطر الأوامر) ═══
python license_generator_gui.py                        # أداة GUI

# ═══ نسخ إلى الفلاشة ═══
Copy-Item "installer_output\StargateDelivery_Setup_v2.0.exe" "F:\" -Force
```

---

## 🐛 15. المشاكل المعروفة والحلول

### المشكلة 1: صفحة التحديث لا تعمل عند الزبون
- **السبب:** كان يحاول استخدام `pythonw.exe app.py` لإعادة التشغيل
- **الحل:** تم إصلاحه ليكتشف تلقائياً وضع EXE ويستخدم `StargateDelivery.exe`
- **الملفات المعدلة:** `app.py` (سطر ~11950) و `ota_updater.py` (سطر ~68)

### المشكلة 2: كلمة المرور لا تعمل في غرفة العمليات
- **السبب:** إذا تم تغيير كلمة المرور ونسيانها
- **الحل:** حذف `master_config.json` وإعادة تشغيل السيرفر (يعود للافتراضي)

### المشكلة 3: الترخيص لا يعمل بالرغم من إدخال الكود
- **السبب:** رقم الجهاز غير مطابق
- **الحل:** التأكد من أن رقم الجهاز المعروض عند الزبون هو نفسه المستخدم في التوليد

---

## 📝 16. سجل التغييرات الأخيرة (16 سبتمبر 2026)

### ما تم إنجازه اليوم:
1. ✅ **ترقية غرفة العمليات (CRM)** - إدارة كاملة لبيانات الزبائن مع بحث وتعديل
2. ✅ **نظام Cloud Kill Switch** - إيقاف التراخيص عن بعد عبر Firebase
3. ✅ **ربط Firebase** - رابط: `https://stargate-experts-default-rtdb.firebaseio.com/`
4. ✅ **إصلاح نظام التحديثات** - التحديث يعمل الآن بشكل صحيح عند الزبون
5. ✅ **بناء النسخة v2.0** - ملف التثبيت جاهز ومنسوخ على الفلاشة
6. ✅ **تاب إعدادات السحابة** - في غرفة العمليات لحفظ رابط Firebase

---

## 🔗 17. الروابط المهمة

| الرابط | الوصف |
|--------|-------|
| `http://localhost:8085` | البرنامج الرئيسي |
| `http://localhost:8085/sg_master` | غرفة العمليات |
| `http://localhost:8085/admin/updates` | صفحة التحديثات (عند الزبون) |
| `http://localhost:8085/admin/updates/dashboard` | لوحة التحديثات المركزية |
| `http://localhost:8085/courier/app` | تطبيق السائق |
| `http://localhost:8085/recovery` | استرداد الحسابات |
| `http://localhost:8085/system-health` | صحة النظام |
| [Firebase Console](https://console.firebase.google.com/) | لوحة تحكم Firebase |
| [Google AI Studio](https://aistudio.google.com/) | مفتاح Gemini AI |

---

> [!TIP]
> **نصيحة للموظف الجديد:** ابدأ بتشغيل `python app.py` ثم افتح `http://localhost:8085/sg_master` في المتصفح لتفهم النظام بشكل كامل.

---

**تم إعداد هذا الدليل بواسطة نظام Stargate Enterprise | 2026**
