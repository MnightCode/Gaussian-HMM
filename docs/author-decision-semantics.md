# Авторська семантика рішень bull/bear/neutral — буквальний код-трейс

**Мета документа:** відповісти буквально, без вигаданої state machine, на питання:
що робить авторський код **після** `bull`, **після** `bear`, що означає `neutral`
для вже відкритої/обраної факторної моделі, і чи рішення тримається до наступної
зміни, чи портфель перебудовується щодня.

**Джерело:** авторський вихідний код `HMMHybrid` (QuantConnect gist, наданий
користувачем повністю в цій розмові). Нижче — **дослівні цитати** коду з
покроковим трасуванням; жодна логіка не вигадана й не додана.

---

## 1. Дослівний код (релевантні фрагменти)

```python
class HMMHybrid(QCAlgorithm):

    def Initialize(self):
        #Switch value for each regime
        self.switch = 'neutral'
        self.AddUniverse(self.CoarseSelectionFunction, self.FineSelectionFunction)
        spy = self.AddEquity("SPY", Resolution.Minute)
        self.SetStartDate(2017, 8, 30)
        self.SetEndDate(2020, 4, 1)
        self.SetCash(100000)
        self.Schedule.On(self.DateRules.EveryDay(), self.TimeRules.BeforeMarketClose("SPY"), self.MarketClose)
        self.Schedule.On(self.DateRules.MonthStart("SPY"), \
                 self.TimeRules.AfterMarketOpen("SPY"), \
                 self.Reset)
        ...
        self.Schedule.On(self.DateRules.EveryDay(), self.TimeRules.AfterMarketOpen("SPY"), Action(self.rebalance))
        ...

    def Reset(self):
        if self.switch == 'bear':
            self.FamaFrench()
        else:
            self.GrowthModel()

    def rebalance(self):
        next = self.next = self.train()
        if self.Portfolio.TotalHoldingsValue == 0:
            self.switch = next
            if self.switch == 'bear':
                self.FamaFrench()
            else:
                self.GrowthModel()
            return

        if next == self.switch:
            return

        self.switch = next

        if next == 'neutral':
            return

        # Assign each stock equally.
        if self.switch == 'bear':
            self.FamaFrench()
        else:
            self.GrowthModel()
```

Плюс `FineSelectionFunction` (визначає, які акції взагалі доступні для вибору):

```python
if self.switch == 'bear':
    return self.french_long + self.french_short
else:
    return self.growth_long
```

---

## 2. Розклад виконання (коли що запускається)

- `self.switch = 'neutral'` — початкове значення в `Initialize()`.
- `rebalance()` — запускається **щодня**, `AfterMarketOpen("SPY")`.
- `Reset()` — запускається **раз на місяць**, `MonthStart`, `AfterMarketOpen("SPY")`.
- `train()` (наш `hmm_standalone.train()`, звірено раніше) викликається **всередині
  `rebalance()`** щодня — тобто `raw_decision` обчислюється **щодня**, без пропусків.

---

## 3. Буквальне трасування `rebalance()` по гілках

### Гілка A — портфель порожній (`TotalHoldingsValue == 0`, лише перший день)
```python
self.switch = next
if self.switch == 'bear': self.FamaFrench()
else: self.GrowthModel()
```
→ **Навіть якщо `next == 'neutral'`**, спрацьовує `else: self.GrowthModel()`.
Тобто в самому першому дні алгоритм **завжди відкриває позицію** (Growth за
замовчуванням, Fama–French лише якщо перший `raw_decision` — `bear`); `neutral`
у цій гілці **не означає «нічого не робити»** — воно трактується як «не bear»
→ Growth.

### Гілка B — `next == self.switch` (сьогоднішнє рішення дорівнює поточному
значенню `self.switch`)
```python
return
```
→ **Нічого не відбувається.** Ні `self.switch`, ні портфель не змінюються.
Це охоплює: повторний `bull` при `switch=='bull'`; повторний `bear` при
`switch=='bear'`; **і повторний `neutral` при `switch=='neutral'`**.

### Гілка C — `next != self.switch` і `next == 'neutral'`
```python
self.switch = next      # <-- self.switch ЛІТЕРАЛЬНО стає 'neutral'
if next == 'neutral':
    return               # <-- портфель НЕ перебудовується цього дня
```
→ **Ключовий факт:** `self.switch` **дійсно перетворюється на `'neutral'`**
(це не «утримання» попереднього bull/bear значення — значення буквально
змінюється). Але **портфель фізично не чіпається** цього дня: функція
повертається до виклику `FamaFrench()`/`GrowthModel()`. Тобто фактичні позиції
залишаються тими, якими були встановлені останнім реальним викликом
ребалансування, **доки** `self.switch` дорівнював 'neutral' і **не з'явиться**
новий `bull`/`bear`, що не дорівнює поточному `self.switch`.

### Гілка D — `next != self.switch` і `next` є `'bull'` або `'bear'`
```python
self.switch = next
if self.switch == 'bear': self.FamaFrench()
else: self.GrowthModel()
```
→ `self.switch` оновлюється, і портфель **перебудовується** до відповідної
факторної моделі (`FamaFrench()` для bear, `GrowthModel()` для bull).

---

## 4. Що це означає буквально (без вигаданого шару)

| Ситуація | `self.switch` після дня | Портфель перебудований? |
|---|---|---|
| `raw_decision` == поточний `switch` (будь-яке з трьох) | не змінюється | ні |
| `raw_decision` = `neutral`, відрізняється від `switch` | стає `'neutral'` | **ні** |
| `raw_decision` = `bull`/`bear`, відрізняється від `switch` | стає `bull`/`bear` | **так** |
| Портфель порожній (перший день) | стає `next` | **так, завжди** (навіть якщо `next=='neutral'` → Growth) |

**Отже:**
- `neutral` **не є «немає рішення»** в сенсі відсутності ефекту на `self.switch` —
  значення змінної буквально стає `'neutral'`. Але воно **є** «немає рішення» в
  сенсі відсутності дії над портфелем цього конкретного дня.
- «Тримається до наступної зміни» — це правда **лише для фактичного складу
  портфеля** (SetHoldings не викликається на neutral-днях), **не** для змінної
  `self.switch`, яка оновлюється буквально щодня, коли значення відрізняється.
- Портфель перебудовується **не щодня**, а **лише в дні, коли `raw_decision`
  відрізняється від поточного `self.switch` І є `bull` або `bear`** (плюс
  щомісячний примусовий `Reset()`, див. нижче).

## 5. Щомісячний `Reset()` — окремий, незалежний механізм

```python
def Reset(self):
    if self.switch == 'bear':
        self.FamaFrench()
    else:
        self.GrowthModel()
```
Запускається **раз на місяць** (перший торговий день місяця), **незалежно** від
того, чи змінювалось щось у `rebalance()` того ж дня. Використовує **поточне**
значення `self.switch` на той момент. Оскільки перевіряється лише
`== 'bear'`, а не `== 'bull'`, — **якщо `self.switch` у цей момент дорівнює
`'neutral'`, спрацьовує `else: GrowthModel()`**. Тобто для цього конкретного
щомісячного примусового ребалансування `neutral` трактується **так само, як
`bull`** (обидва → Growth), а не як «нічого не робити».

## 6. Залежність `FineSelectionFunction` від `self.switch`
```python
if self.switch == 'bear':
    return self.french_long + self.french_short
else:
    return self.growth_long
```
Список акцій для відбору теж залежить від поточного `self.switch` за тим самим
правилом «bear vs не-bear» (тобто `neutral` тут знову трактується як «не
bear» → growth-список). **Відкрите питання, яке НЕ стверджую напевно:**
точний порядок виконання QuantConnect між Coarse/FineSelection (яка сама
запускається за власним розкладом universe-refresh) і щоденним
`rebalance()` у межах одного торгового дня — тобто чи `FineSelectionFunction`
того ж дня бачить `self.switch` **до** чи **після** оновлення в `rebalance()`
цього дня. Це деталь виконання QC-рушія, яку не можна встановити лише з
тексту скрипта без запуску на самій платформі; тому позначаю це відкритим
питанням, а не стверджую напевно.

## 7. Підсумок — відповіді на прямі питання

- **Що відбувається після `bull`:** `self.switch` стає `'bull'`; портфель
  перебудовується на `GrowthModel()` (якщо це була зміна відносно попереднього
  `switch`); тримається без повторних викликів `SetHoldings`, доки не прийде
  інше значення `raw_decision`, відмінне від поточного `switch`.
- **Що відбувається після `bear`:** аналогічно, `self.switch` → `'bear'`,
  портфель → `FamaFrench()`.
- **Що означає `neutral` для вже відкритої моделі:** портфель **не
  перебудовується** цього дня (SetHoldings не викликається), фактичні позиції
  лишаються тими, що були; але внутрішня змінна `self.switch` **буквально
  дорівнює** `'neutral'`, доки не прийде новий `bull`/`bear`. У щомісячному
  `Reset()` та в `FineSelectionFunction`, `neutral`-значення `self.switch`
  трактується як «не bear» → Growth-гілка (тобто **не** нейтрально, а як bull
  для цих двох конкретних місць коду).
- **Рішення тримається чи портфель перебудовується щодня:** портфель
  перебудовується **тільки в дні фактичної зміни** `raw_decision` на `bull`/
  `bear` (плюс примусово раз на місяць через `Reset()`); у решту днів (включно
  з усіма послідовними `neutral`) — портфель незмінний.

---

## Що НЕ стверджується цим документом
- Не вводиться жодна «персистентна ринкова стадія» — усе вище є буквальним
  описом **портфельного** виконання (яку модель тримати), а не інтерпретацією
  ринкового режиму.
- Не стверджується оцінка якості чи корисності цієї механіки — лише буквальний
  опис того, що робить код.
- П.6 (порядок виконання QC) залишено як відкрите питання, а не факт.
