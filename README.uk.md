# Broadlink (DAB-LABS async) for Home Assistant

*[Read this in English](README.md)*

Альтернативна інтеграція Broadlink для Home Assistant, побудована на
[DAB-LABS/python-broadlink](https://github.com/DAB-LABS/python-broadlink) —
підтримуваному асинхронному форку `mjg59/python-broadlink`, який ядро HA
використовує зараз і який не отримує змін з 2024 року.

Домен інтеграції: **`broadlink_dablabs`** — окремий від штатного `broadlink`,
тому обидві інтеграції можуть працювати одночасно без конфліктів.

## Навіщо це

- `mjg59/python-broadlink` (залежність штатної інтеграції) не приймає змін з
  2024 року, тому нові пристрої (наприклад RM5 Plus) не потрапляють у HA
  офіційно.
- DAB-LABS підтримує форк саме для того, щоб HA міг отримувати виправлення й
  нові пристрої, включно з RM5 Plus (`0x5224`).
- Ця інтеграція **вбудовує (вендорить)** код DAB-LABS напряму в
  `custom_components/broadlink_dablabs/blk/`, а не тягне його як pip-пакет —
  PyPI-дистрибутив DAB-LABS (`python-broadlink`) встановлюється під тим самим
  імпортованим ім'ям `broadlink`, що й пакет штатної інтеграції, тож два pip-
  пакети конфліктували б в одному venv. Вендоринг це повністю знімає.
- Усі виклики бібліотеки — справжній нативний `asyncio` (UDP-транспорт,
  `asyncio.Lock`, `asyncio.Queue`), тому інтеграція викликає їх напряму через
  `await`, без `hass.async_add_executor_job`.

## Що підтримується

Платформи: `remote`, `infrared`, `radio_frequency`, `time`, `select`,
`sensor`, `switch`, `light`, `climate` — для тих самих родин пристроїв, що й
у штатній інтеграції (RM mini/pro/4/5 Plus, A1/A2, SP1-4, MP1/MP1S, BG1,
LB1/LB2, Hysen-термостати).

**RM5 Plus підтримується "з коробки"**: `INFRARED` + `REMOTE` + `SWITCH` +
`RADIO_FREQUENCY` (експериментально, без підтвердження на залізі), без
ручного патчингу бібліотеки після кожного оновлення HAOS.

### Свідомо не перенесено

- Застаріла YAML-платформа `switch:` (в самому ядрі позначена як deprecated) —
  усі пристрої додаються через Config Flow (UI).
- DHCP-автовиявлення — вимкнено навмисно, щоб не дублювати сповіщення поруч
  зі штатною інтеграцією `broadlink`. Пристрої додаються вручну за IP.

### Відомі обмеження

Платформи `infrared` і `radio_frequency` залежать від відносно нових базових
доменів ядра HA (`homeassistant.components.infrared` /
`homeassistant.components.radio_frequency`, пакети `infrared-protocols` /
`rf-protocols`). Якщо ваша версія HA ще їх не має, впадуть лише ці дві
платформи в лозі — решта (`remote`, `switch`, `sensor`, `light`, `climate`,
`select`, `time`) працюватимуть нормально.

Потрібен Python 3.13+ у контейнері HA (використовується синтаксис generic-
параметрів за замовчуванням, PEP 696) — це вже вимога самого ядра Home
Assistant у поточних релізах.

## Встановлення через HACS (Custom repository)

1. HACS → три крапки вгорі праворуч → **Custom repositories**.
2. URL: `https://github.com/NetZhizni/ha-broadlink-dablabs`, категорія:
   **Integration**.
3. Знайдіть "Broadlink (DAB-LABS async)" у HACS → Download.
4. Перезапустіть Home Assistant.
5. Settings → Devices & Services → Add Integration → **Broadlink (DAB-LABS
   async)** → введіть IP-адресу пристрою (наприклад, RM5 Plus).

## Ручне встановлення (без HACS)

Скопіюйте `custom_components/broadlink_dablabs/` у `config/custom_components/`
вашого HA і перезапустіть Home Assistant.

## Іконка

Інтеграція постачає власну іконку/лого (`custom_components/broadlink_dablabs/brand/`),
ідентичні тим, що використовує штатна інтеграція `broadlink` у
[home-assistant/brands](https://github.com/home-assistant/brands). З Home
Assistant 2026.3+ кастомні інтеграції можуть постачати brand-зображення прямо
у своїй теці (`brand/icon.png`, `brand/logo.png` тощо) — окремий запит до
репозиторію brands більше не потрібен, іконка з'явиться в UI одразу після
встановлення.

## Ліцензія

MIT, див. [LICENSE](LICENSE). Код у `custom_components/broadlink_dablabs/blk/`
вендорено з [DAB-LABS/python-broadlink](https://github.com/DAB-LABS/python-broadlink)
під його власною MIT-ліцензією — див.
[blk/LICENSE](custom_components/broadlink_dablabs/blk/LICENSE).
