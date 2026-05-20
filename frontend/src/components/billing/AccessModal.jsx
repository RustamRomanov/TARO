import { useEffect, useMemo, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import Button from '../ui/Button';
import { getInitData, getInitDataStrict } from '../../lib/initData';
import { postJson, requestJson } from '../../lib/apiClient';

const API_BASE = import.meta.env.VITE_API_URL || '';
const TOPUP_OPTIONS = [50, 100, 200];

/** Кнопки выбора срока VIP: выше ~на 30 % и заметнее как интерактив. */
const VIP_TIER_CHOICE_BUTTON_CLASS =
  'flex min-h-[3.25rem] w-full items-center justify-between rounded-xl border-2 border-amber-400/50 bg-gradient-to-b from-amber-500/[0.22] to-black/45 px-4 py-3 text-left shadow-md shadow-black/30 outline-none transition hover:border-amber-300/60 hover:from-amber-500/30 hover:shadow-lg hover:shadow-amber-950/25 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-60 disabled:active:scale-100';

function detailToMessage(d) {
  if (typeof d === 'string') return d.trim();
  if (Array.isArray(d)) {
    const first = d[0];
    const s = first?.msg ?? first?.message ?? (typeof first === 'string' ? first : null);
    return typeof s === 'string' ? s.trim() : null;
  }
  if (d && typeof d === 'object') {
    const s = d.description ?? d.msg ?? d.message;
    return typeof s === 'string' ? s.trim() : null;
  }
  return null;
}
const MAX_SUPPORT_IMAGE_BYTES = 2 * 1024 * 1024;
const AGREEMENT_TEXT = `1. ВСТУПЛЕНИЕ

Добро пожаловать в ASTROV - проект, объединивший многолетние исследования в области нумерологии, астрологии, физиогномики, хиромантии и психологии образов.

За каждым расчетом, каждым анализом, каждым толкованием стоят тысячи часов изучения древних знаний, современной аналитики и сотни тысяч обработанных данных. Мы не просто генерируем текст - мы используем модели, обученные на огромном массиве информации, чтобы дать вам максимально точную, структурированную и полезную обратную связь.

Наша миссия - помочь вам лучше понять себя, свои таланты, ограничения и возможности. Но при этом мы всегда остаемся в рамках развлекательного и ознакомительного формата.

Пожалуйста, внимательно прочитайте настоящее Пользовательское соглашение (далее - Соглашение) перед началом использования Сервиса. Подтверждая его, вы заключаете с нами юридически значимый договор на условиях, изложенных ниже.

2. ОСНОВНЫЕ ПОЛОЖЕНИЯ

2.1. Сервис ASTROV (далее - Сервис) представляет собой программу для ЭВМ, доступную через Telegram Mini App, и набор сопутствующих услуг по самопознанию, основанных на математических алгоритмах, статистических данных и технологиях искусственного интеллекта.

2.2. Сервис предлагает следующие виды аналитики:
- Нумерологический расчет 22 Ключа судьбы - авторская мандала на основе даты рождения, 22 аркана;
- Астрологический прогноз - персонализированный гороскоп на день/неделю/месяц по солнечному знаку;
- Натальная карта - расчет положения планет, асцендента, домов и аспектов (требуется время и место рождения);
- Толкование сновидений - диалоговый AI-коучинг с сохранением истории и аналитикой;
- Психологический портрет - определение черт характера, талантов, рекомендаций по стилю и уходу;
- Хиромантия - чтение линий, бугров и знаков;
- Совместимость по фотографиям - анализ гармонии двух лиц.

2.3. Все результаты, генерируемые Сервисом, носят исключительно информационно-развлекательный характер. Они не являются:
- медицинскими, психологическими, психиатрическими или терапевтическими заключениями;
- юридическими, финансовыми или инвестиционными консультациями;
- предсказаниями, обязательными к исполнению;
- официальными диагностическими методиками.

2.4. Используя Сервис, вы подтверждаете, что осознаете: любые решения, принятые вами на основе полученной информации, являются вашим личным выбором и ответственностью. Правообладатель Сервиса не несет ответственности за последствия таких решений.

3. ПРЕДМЕТ СОГЛАШЕНИЯ. ЛИЦЕНЗИЯ

3.1. Правообладатель (Администрация Сервиса) предоставляет Пользователю на условиях простой (неисключительной) лицензии право использования программы для ЭВМ ASTROV в пределах функциональности, доступной через интерфейс Telegram Mini App.

3.2. Лицензия предоставляется на срок использования Сервиса и действует на территории всего мира.

3.3. Пользователь не вправе:
- распространять, копировать, модифицировать, декомпилировать программу;
- использовать Сервис в коммерческих целях без отдельного письменного соглашения;
- осуществлять автоматизированный сбор данных (парсинг) любыми способами.

3.4. Все исключительные права на программу, алгоритмы, дизайн, тексты, авторские методики (22 Ключа судьбы, Мандала судьбы и др.) принадлежат Правообладателю и охраняются законодательством об интеллектуальной собственности.

4. ПЕРСОНАЛЬНЫЕ ДАННЫЕ И БИОМЕТРИЯ

4.1. Для корректной работы Сервиса Пользователь предоставляет следующие данные:
- дата рождения (для нумерологических и астрологических расчетов);
- время и место рождения (опционально, для натальной карты);
- имя (для персонализации обращений);
- пол и город (опционально - для улучшения качества прогнозов);
- фотографии лица и/или ладоней (для услуг «Психологический портрет», «Хиромантия», «Совместимость по фото»).

4.2. Обработка биометрических персональных данных.
Предоставляя фотографии, Пользователь дает прямое, осознанное и добровольное согласие на их обработку методами, описанными в настоящем Соглашении. Обработка включает: сбор, систематизацию, накопление, хранение, уточнение (обновление, изменение), извлечение, использование, передачу (в объеме, необходимом для оказания услуги), обезличивание, блокирование, удаление, уничтожение.

4.3. Цели обработки биометрических данных:
- идентификация и анализ черт лица/линий ладони для формирования отчета;
- улучшение и обучение алгоритмов искусственного интеллекта (на обезличенных данных);
- внутренняя статистика и контроль качества.

4.4. Хранение и удаление.
Изображения хранятся в зашифрованном виде на защищенных серверах. Срок хранения - до момента отзыва Пользователем согласия либо до достижения целей обработки, но не более 30 дней с момента последнего использования Пользователем соответствующей функции. Пользователь может в любой момент удалить ранее загруженные фото через интерфейс Сервиса или письменным запросом.

4.5. Отзыв согласия.
Пользователь вправе отозвать согласие на обработку биометрических данных, направив уведомление на gregoryastrov@yandex.ru. При отзыве все фотографии Пользователя удаляются, а доступ к соответствующим функциям Сервиса прекращается.

4.6. Гарантии конфиденциальности.
Администрация не передает фотографии Пользователя третьим лицам, за исключением случаев, прямо предусмотренных законодательством РФ. Обезличенные данные могут использоваться для обучения алгоритмов без возможности идентификации Пользователя.

5. ПРАВА ПОЛЬЗОВАТЕЛЯ НА КОНТЕНТ

5.1. Пользователь сохраняет авторские права на тексты сновидений, вопросы, комментарии и иные пользовательские материалы, размещенные в Сервисе.

5.2. Размещая такие материалы, Пользователь безвозмездно предоставляет Администрации неисключительную, бессрочную, действующую на всей территории мира лицензию на их обработку, хранение, использование в обезличенном виде для улучшения качества Сервиса и обучения алгоритмов.

6. ОГРАНИЧЕНИЕ ОТВЕТСТВЕННОСТИ И ОТКАЗ ОТ ГАРАНТИЙ

6.1. Сервис предоставляется КАК ЕСТЬ (AS IS). Правообладатель не гарантирует:
- непрерывную, безошибочную или бесперебойную работу;
- соответствие результатов ожиданиям Пользователя;
- точность, полноту или актуальность предоставляемой информации.

6.2. Правообладатель не несет ответственности за:
- любые прямые или косвенные убытки, возникшие в результате использования или невозможности использования Сервиса;
- решения, принятые Пользователем на основе полученных отчетов;
- содержание внешних ссылок, размещенных в Сервисе;
- действия третьих лиц, получивших несанкционированный доступ к данным Пользователя по его вине.

6.3. Здоровье и безопасность.
Если Пользователь испытывает серьезные эмоциональные трудности, депрессию, суицидальные мысли или иные состояния, требующие профессионального вмешательства, - ему необходимо немедленно обратиться к квалифицированному специалисту. Сервис ASTROV не является заменой психологической, психиатрической или медицинской помощи.

6.4. Возрастные ограничения.
Сервис предназначен для лиц старше 18 лет. Если Пользователю нет 18 лет, использование Сервиса допускается только с согласия и под контролем родителей или законных представителей.

7. ПЛАТНЫЕ УСЛУГИ

7.1. Некоторые функции Сервиса могут предоставляться на платной основе (Тариф VIP, пополнение баланса). Условия оплаты, действующие тарифы и порядок оказания платных услуг размещены в интерфейсе Сервиса перед оплатой и являются публичной офертой.

7.2. Реферальная программа. Сервис может начислять бонусные средства на внутренний баланс за приглашение новых пользователей по правилам, указанным в интерфейсе. Такие бонусы используются только для оплаты функций Сервиса внутри приложения и не являются выплатой «наличными», если иное прямо не предусмотрено Администрацией.

8. ЗАКЛЮЧИТЕЛЬНЫЕ ПОЛОЖЕНИЯ

8.1. Настоящее Соглашение вступает в силу с момента его акцепта Пользователем и действует бессрочно.

8.2. Администрация Сервиса вправе вносить изменения в Соглашение в одностороннем порядке. Новая редакция вступает в силу с момента ее публикации в Сервисе. Продолжение использования Сервиса после изменения Соглашения означает согласие Пользователя с новой редакцией.

8.3. Все споры, возникающие из настоящего Соглашения или в связи с ним, подлежат разрешению в суде по месту нахождения Правообладателя в порядке, установленном законодательством РФ.

8.4. По всем вопросам, связанным с исполнением настоящего Соглашения, обработкой персональных данных и работой Сервиса, Пользователь может обращаться по адресу: gregoryastrov@yandex.ru.

АКЦЕПТ СОГЛАШЕНИЯ

Я, {{ user_first_name }}, подтверждаю, что:
- ознакомился с настоящим Пользовательским соглашением в полном объеме;
- понимаю его содержание и добровольно принимаю все условия;
- осознаю развлекательный характер Сервиса и не считаю полученные результаты медицинскими, психологическими или юридическими заключениями;
- даю согласие на обработку моих персональных данных, включая биометрические, в целях и порядке, указанных в Соглашении.`;

const VIP_TARIFF_OFFER_TEXT = `ПУБЛИЧНАЯ ОФЕРТА НА ТАРИФ VIP

1. ПРЕДМЕТ ОФЕРТЫ

1.1. Тариф VIP — разовая покупка доступа к расширенным функциям Сервиса ASTROV на определённый срок. Пользователь приобретает право пользоваться всеми платными функциями в течение оплаченного периода.

1.2. Автопродление отсутствует. По окончании оплаченного периода доступ завершается; для продолжения необходимо приобрести Тариф VIP заново.

2. ТАРИФЫ И ОПЛАТА

2.1. Действующие варианты Тарифа VIP и цены указаны в интерфейсе Сервиса на момент оплаты.

2.2. Оплата производится единоразово через защищённый платёжный интерфейс ЮKassa. Данные банковской карты не сохраняются на серверах Администрации.

2.3. Момент активации доступа — успешное зачисление оплаты (подтверждение от платёжного агрегатора).

3. ЛИМИТЫ И УСЛОВИЯ ИСПОЛЬЗОВАНИЯ

3.1. Тариф VIP предоставляет безлимитный доступ ко всем платным функциям Сервиса (Таро, толкование снов, Психологический портрет, Хиромантия, совместимость по фото, гороскопы, натальная карта, Матрица судьбы и др.) в течение оплаченного периода. Дневных ограничений на количество запросов нет.

3.2. Защита от злоупотребления: при более 30 запросах подряд за один час по одной функции (например, Таро или сны) доступ может быть временно приостановлен с сообщением «Система перегружена. Повторите попытку позже.»

3.3. Без Тарифа VIP функции оплачиваются по балансу. Текущие тарифы: персональный гороскоп: бесплатно; толкование сна: бесплатно; расклад Таро: 10 ₽; Психологический портрет / Хиромантия / совместимость по фото: 10 ₽; натальная карта: 50 ₽; Матрица судьбы: 50 ₽; совместимость по датам: 20 ₽. Стоимость может быть изменена Администрацией. Ранее внесённые пользователем средства списываются по тарифам, действовавшим на момент пополнения.

3.4. Администрация вправе вводить иные ограничения при необходимости, уведомляя Пользователя через интерфейс Сервиса.

4. ВОЗВРАТ

4.1. Возврат денежных средств осуществляется в случаях, предусмотренных законодательством РФ (техническая невозможность оказать услугу по вине Администрации, ошибочное списание и т.п.).

4.2. Заявление на возврат направляется на gregoryastrov@yandex.ru с указанием даты, суммы и причины.

5. ИЗМЕНЕНИЯ

5.1. Администрация вправе изменять стоимость и условия Тарифа VIP в одностороннем порядке. Изменения вступают в силу с момента публикации в Сервисе.

5.2. Оплаченный ранее период действует на условиях, действовавших на момент оплаты.

6. РЕФЕРАЛЬНАЯ ПРОГРАММА

6.1. Администрация вправе начислять Пользователю бонусные средства на баланс Сервиса за привлечение новых пользователей по реферальной ссылке, в размере и на условиях, указанных в интерфейсе Сервиса на момент успешной оплаты приглашённым лицом.

6.2. Бонус начисляется после фактического поступления оплаты: пополнение баланса или покупка тарифа. Бонусные рубли используются только внутри Сервиса для оплаты функций и не являются самостоятельным денежным требованием к Администрации, если иное прямо не указано в интерфейсе.

7. КОНТАКТЫ

7.1. По всем вопросам: gregoryastrov@yandex.ru.`;

function openExternal(url) {
  if (!url) return;
  const tg = window?.Telegram?.WebApp;
  if (tg?.openLink) {
    tg.openLink(url, { try_instant_view: false });
    return;
  }
  window.location.href = url;
}

function loadYooWidgetScript() {
  if (window?.YooMoneyCheckoutWidget) return Promise.resolve(true);
  return new Promise((resolve, reject) => {
    const existing = document.querySelector('script[data-yookassa-widget="1"]');
    if (existing) {
      existing.addEventListener('load', () => resolve(true), { once: true });
      existing.addEventListener('error', () => reject(new Error('Не удалось загрузить модуль оплаты.')), { once: true });
      return;
    }
    const script = document.createElement('script');
    script.src = 'https://yookassa.ru/checkout-widget/v1/checkout-widget.js';
    script.async = true;
    script.dataset.yookassaWidget = '1';
    script.onload = () => resolve(true);
    script.onerror = () => reject(new Error('Не удалось загрузить модуль оплаты.'));
    document.body.appendChild(script);
  });
}

function formatStars(balanceCents) {
  const stars = Math.max(0, Math.floor((Number(balanceCents || 0)) / 100));
  return `${stars} ₽`;
}

const TARIFF_TEXT = `Тарифы использования приложения ASTROV:
- Персональный гороскоп - бесплатно
- Толкование сна - бесплатно
- Расклад Таро - 10 ₽
- Психологический портрет - 10 ₽
- Хиромантия - 10 ₽
- Совместимость по фото - 10 ₽
- Натальная карта - 50 ₽
- Матрица судьбы - 50 ₽
- Совместимость по датам - 20 ₽

Стоимость услуг могут быть изменены Администрацией в одностороннем порядке. Новая стоимость применяется к пополнениям, совершённым после публикации изменений. Ранее внесённые пользователем средства списываются по тарифам, действовавшим на момент пополнения.`;

export default function AccessModal({
  open,
  onClose,
  title = 'Оформите доступ',
  message = 'Этот сервис доступен по подписке или по балансу.',
  initialTab = 'vip',
  /** При открытии модалки сразу показать форму обращения в поддержку (если вызывающий код передаёт true). */
  initialSupportView = false,
  status = 'free',
  balanceCents = 0,
  subscriptionNextChargeAt = null,
  subscriptionCanceledAt = null,
  subscriptionEndDate = null,
  isTrialUsed = false,
  refetchAuth = async () => {},
  showSubscription = true,
}) {
  const [loadingType, setLoadingType] = useState('');
  const [error, setError] = useState('');
  const [tab, setTab] = useState('vip');
  const [showAgreementModal, setShowAgreementModal] = useState(false);
  const [showOfferModal, setShowOfferModal] = useState(false);
  const [agreementAccepted, setAgreementAccepted] = useState(false);
  const [selectedTopup, setSelectedTopup] = useState(50);
  const [showTariffModal, setShowTariffModal] = useState(false);
  const [showSupportView, setShowSupportView] = useState(false);
  const [supportMessage, setSupportMessage] = useState('');
  const [supportImage, setSupportImage] = useState(null);
  const [supportSending, setSupportSending] = useState(false);
  const [supportSuccess, setSupportSuccess] = useState('');
  const [cancelConfirmed, setCancelConfirmed] = useState(false);
  const [checkoutToken, setCheckoutToken] = useState('');
  const [checkoutUrl, setCheckoutUrl] = useState('');
  const [isCheckoutLoading, setIsCheckoutLoading] = useState(false);
  const [createdPaymentId, setCreatedPaymentId] = useState('');
  const widgetRef = useRef(null);
  const modalBodyRef = useRef(null);
  const paymentResolvedRef = useRef(false);
  const initData = getInitDataStrict() || getInitData();
  const isPaid = status === 'full_access' || status === 'trial';
  const hasSubscriptionUi = Boolean(showSubscription);
  const showPaidUi = hasSubscriptionUi && isPaid;
  const hasActivePayment = Boolean(checkoutToken || checkoutUrl);
  // For active paid access, old canceled_at should not block current subscription controls.
  const isCanceled = !isPaid && Boolean(subscriptionCanceledAt);
  const userFirstName = String(window?.Telegram?.WebApp?.initDataUnsafe?.user?.first_name || 'Пользователь').trim();

  const agreementText = useMemo(
    () => AGREEMENT_TEXT.replace('{{ user_first_name }}', userFirstName || 'Пользователь'),
    [userFirstName]
  );

  useEffect(() => {
    if (!open || !checkoutToken) return undefined;
    let cancelled = false;
    setIsCheckoutLoading(true);

    const cleanupWidget = () => {
      try {
        if (widgetRef.current?.destroy) widgetRef.current.destroy();
      } catch (_) {}
      widgetRef.current = null;
    };

    (async () => {
      try {
        await loadYooWidgetScript();
        if (cancelled || !window?.YooMoneyCheckoutWidget) return;
        const checkout = new window.YooMoneyCheckoutWidget({
          confirmation_token: checkoutToken,
          error_callback: (widgetError) => {
            const msg = widgetError?.message || 'Ошибка виджета оплаты.';
            setError(String(msg));
            setIsCheckoutLoading(false);
          },
        });
        widgetRef.current = checkout;

        checkout.on('success', async () => {
          if (paymentResolvedRef.current) return;
          paymentResolvedRef.current = true;
          cleanupWidget();
          setCheckoutToken('');
          setCreatedPaymentId('');
          setIsCheckoutLoading(false);
          await refetchAuth();
          setError('');
          handleClose();
        });

        checkout.on('fail', () => {
          cleanupWidget();
          setCheckoutToken('');
          setCreatedPaymentId('');
          setIsCheckoutLoading(false);
          setError('Оплата не завершена. Попробуйте еще раз.');
        });

        checkout.on('complete', async () => {
          if (paymentResolvedRef.current) return;
          paymentResolvedRef.current = true;
          cleanupWidget();
          setCheckoutToken('');
          setCreatedPaymentId('');
          setIsCheckoutLoading(false);
          await refetchAuth();
          handleClose();
        });

        checkout.render('yookassa-payment-form');
        setIsCheckoutLoading(false);
      } catch (e) {
        setIsCheckoutLoading(false);
        setError(e?.message || 'Не удалось запустить форму оплаты.');
      }
    })();

    return () => {
      cancelled = true;
      cleanupWidget();
    };
  }, [open, checkoutToken, refetchAuth]);

  useEffect(() => {
    if (!open || !createdPaymentId) return undefined;
    let cancelled = false;
    let inFlight = false;
    const startedAt = Date.now();
    const maxPollMs = 5 * 60 * 1000;

    const pollStatus = async () => {
      if (cancelled || inFlight) return;
      if (Date.now() - startedAt > maxPollMs) return;
      inFlight = true;
      try {
        const { ok, data } = await requestJson({
          url: `${API_BASE}/api/payments/status/${encodeURIComponent(createdPaymentId)}?init_data=${encodeURIComponent(initData)}`,
          dedupe: false,
          cacheTtlMs: 1000,
        });
        if (!ok) return;
        const current = String(data?.status || '');
        if (current === 'succeeded') {
          if (paymentResolvedRef.current) return;
          paymentResolvedRef.current = true;
          try {
            if (widgetRef.current?.destroy) widgetRef.current.destroy();
          } catch (_) {}
          widgetRef.current = null;
          setCheckoutToken('');
          setCheckoutUrl('');
          setCreatedPaymentId('');
          setIsCheckoutLoading(false);
          setError('');
          await refetchAuth();
          handleClose();
          return;
        }
        if (current === 'failed' || current === 'canceled') {
          setCheckoutToken('');
          setCheckoutUrl('');
          setCreatedPaymentId('');
          setIsCheckoutLoading(false);
          setError('Оплата не завершена. Попробуйте еще раз.');
          return;
        }
      } catch (_) {
      } finally {
        inFlight = false;
        if (!cancelled) {
          const elapsed = Date.now() - startedAt;
          const nextDelay = elapsed < 60_000 ? 2500 : 5000;
          window.setTimeout(pollStatus, nextDelay);
        }
      }
    };

    pollStatus();
    return () => {
      cancelled = true;
    };
  }, [open, createdPaymentId, initData, refetchAuth]);

  useEffect(() => {
    if (!open) return;
    if (!modalBodyRef.current) return;
    modalBodyRef.current.scrollTop = 0;
  }, [open, checkoutToken]);

  useEffect(() => {
    if (!open) return;
    if (!hasSubscriptionUi) {
      setTab('balance');
    } else if (isPaid) {
      setTab('vip');
    } else if (initialTab === 'vip' || initialTab === 'balance') {
      setTab(initialTab);
    } else {
      setTab('balance');
    }
    setAgreementAccepted(false);
    setShowAgreementModal(false);
    setShowOfferModal(false);
    setSelectedTopup(50);
    setShowTariffModal(false);
    setShowSupportView(Boolean(initialSupportView));
    setSupportMessage('');
    setSupportImage(null);
    setSupportSending(false);
    setSupportSuccess('');
    setCancelConfirmed(false);
  }, [open, hasSubscriptionUi, isPaid, initialSupportView, initialTab]);


  const handleClose = () => {
    paymentResolvedRef.current = false;
    try {
      if (widgetRef.current?.destroy) widgetRef.current.destroy();
    } catch (_) {}
    widgetRef.current = null;
    setCheckoutToken('');
    setCheckoutUrl('');
    setCreatedPaymentId('');
    setIsCheckoutLoading(false);
    setLoadingType('');
    setShowAgreementModal(false);
    setShowOfferModal(false);
    onClose?.();
  };

  const createPayment = async (paymentType, amountRub = null) => {
    if (!initData?.trim()) {
      setError('Откройте приложение через Telegram.');
      return;
    }
    setError('');
    paymentResolvedRef.current = false;
    setLoadingType(paymentType + (amountRub ? `_${amountRub}` : ''));
    try {
      const returnUrl = `${window.location.origin}/profile`;
      const { ok, data } = await postJson(`${API_BASE}/api/payments/create`, {
        init_data: initData,
        payment_type: paymentType,
        amount_rub: amountRub,
        return_url: returnUrl,
      });
      if (!ok) throw new Error(detailToMessage(data?.detail) || 'Не удалось создать платеж.');
      const confirmationUrl = String(data?.confirmation_url || '');
      setCreatedPaymentId(String(data?.yookassa_payment_id || ''));
      setCheckoutUrl(confirmationUrl);
      if (paymentType === 'subscription' && data?.recurring_fallback_used) {
        setError('Для этого магазина автопродление сейчас недоступно. Подписка будет оформлена как разовая оплата на месяц.');
      }
      if (data?.confirmation_token) {
        setCheckoutToken(data.confirmation_token);
      } else if (data?.confirmation_url) {
        setCheckoutUrl(confirmationUrl);
        openExternal(confirmationUrl);
      } else {
        throw new Error('Платеж создан без данных подтверждения.');
      }
    } catch (e) {
      setError(e?.message || 'Ошибка оплаты.');
    } finally {
      setLoadingType('');
    }
  };

  const cancelSubscription = async () => {
    if (!initData?.trim()) {
      setError('Откройте приложение через Telegram.');
      return;
    }
    setError('');
    setLoadingType('cancel');
    try {
      const { ok, data } = await postJson(`${API_BASE}/api/payments/subscription/cancel`, {
        init_data: initData,
      });
      if (!ok) throw new Error(detailToMessage(data?.detail) || 'Не удалось отменить подписку.');
      await refetchAuth();
      setCancelConfirmed(false);
    } catch (e) {
      setError(e?.message || 'Ошибка отмены подписки.');
    } finally {
      setLoadingType('');
    }
  };

  const sendSupportAppeal = async () => {
    const text = String(supportMessage || '').trim();
    if (!text) {
      setError('Введите текст обращения.');
      return;
    }
    if (supportImage && supportImage.size > MAX_SUPPORT_IMAGE_BYTES) {
      setError('Размер изображения не должен превышать 2 МБ.');
      return;
    }
    if (!initData?.trim()) {
      setError('Откройте приложение через Telegram.');
      return;
    }
    setError('');
    setSupportSuccess('');
    setSupportSending(true);
    try {
      const form = new FormData();
      form.append('init_data', initData);
      form.append('message', text);
      if (supportImage) form.append('image', supportImage);
      const res = await fetch(`${API_BASE}/api/support/send-form`, {
        method: 'POST',
        body: form,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(detailToMessage(data?.detail) || 'Не удалось отправить обращение.');
      setSupportSuccess('Обращение отправлено. Мы скоро вам ответим в Telegram.');
      setSupportMessage('');
      setSupportImage(null);
    } catch (e) {
      setError(e?.message || 'Не удалось отправить обращение.');
    } finally {
      setSupportSending(false);
    }
  };

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[90] flex items-center justify-center p-3"
          style={{
            paddingTop: 'calc(env(safe-area-inset-top) + 1.5rem)',
            paddingBottom: 'calc(env(safe-area-inset-bottom) + 4.5rem)',
          }}
        >
          <div className="absolute inset-0 bg-black/75 backdrop-blur-sm" onClick={handleClose} aria-hidden />
          <motion.div
            initial={{ y: 24, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 24, opacity: 0 }}
            className="relative z-10 w-full max-w-lg overflow-y-auto overscroll-contain touch-pan-y scrollbar-hide rounded-3xl border border-amber-500/30 bg-[#0b0b1e] p-4 pb-[calc(env(safe-area-inset-bottom)+1rem)]"
            style={{ maxHeight: 'calc(100dvh - env(safe-area-inset-top) - env(safe-area-inset-bottom) - 2.5rem)' }}
            onClick={(e) => e.stopPropagation()}
            ref={modalBodyRef}
          >
            {!showSupportView && (showPaidUi || title || message) ? (
              <>
                <p className="text-amber-300 text-sm font-medium">{showPaidUi ? 'Тариф VIP' : title}</p>
                <p className="text-white/75 text-xs mt-1">
                  {showPaidUi
                    ? (
                      <>
                        Тариф VIP активен.{' '}
                        <span className="text-emerald-300 text-[13px] font-semibold">
                          Безлимитный доступ ко всем функциям приложения
                        </span>{' '}
                        до окончания оплаченного периода.
                      </>
                    )
                    : message}
                </p>
              </>
            ) : null}

            {checkoutToken ? (
              <div className="mt-3 rounded-2xl border border-amber-400/25 bg-black/30 p-3">
                <div id="yookassa-payment-form" className="min-h-[280px] w-full" />
                {isCheckoutLoading ? <p className="text-white/50 text-[11px] mt-2">Загружаю форму оплаты...</p> : null}
                <p className="text-white/45 text-[11px] mt-2">
                  Если оплата через банк подтверждается дольше обычного, подождите 5-15 секунд: статус обновится автоматически.
                </p>
                <Button
                  size="md"
                  variant="ghost"
                  className="w-full mt-3"
                  onClick={() => {
                    setCheckoutToken('');
                    setCheckoutUrl('');
                    setCreatedPaymentId('');
                  }}
                >
                  Отменить оплату
                </Button>
              </div>
            ) : null}
            {!checkoutToken && checkoutUrl ? (
              <div className="mt-3 rounded-2xl border border-amber-400/25 bg-black/30 p-3 space-y-3">
                <p className="text-white/70 text-xs">
                  Открываем оплату СБП. Если окно не появилось, нажмите кнопку ниже.
                </p>
                <Button size="md" className="w-full" onClick={() => openExternal(checkoutUrl)}>
                  Перейти к оплате
                </Button>
                <Button
                  size="md"
                  variant="ghost"
                  className="w-full"
                  onClick={() => {
                    setCheckoutUrl('');
                    setCreatedPaymentId('');
                  }}
                >
                  Вернуться к балансу
                </Button>
              </div>
            ) : null}
            {null}

            {!checkoutToken && !showSupportView ? (
              <>
                {hasSubscriptionUi ? (
                  <div className="mt-3 grid grid-cols-2 gap-2 rounded-xl border border-white/10 bg-white/[0.02] p-1">
                    <button
                      type="button"
                      onClick={() => setTab('balance')}
                      className={`rounded-lg py-2 text-xs ${tab === 'balance' ? 'bg-amber-300/15 text-amber-200' : 'text-white/65'}`}
                    >
                      Баланс
                    </button>
                    <button
                      type="button"
                      onClick={() => setTab('vip')}
                      className={`rounded-lg py-2 text-xs ${tab === 'vip' ? 'bg-amber-300/15 text-amber-200' : 'text-white/65'}`}
                    >
                      Тариф VIP
                    </button>
                  </div>
                ) : null}

                {showPaidUi && tab === 'vip' ? (
                  <div className="mt-3 space-y-3">
                    <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-3 space-y-2">
                      {subscriptionNextChargeAt && !isCanceled ? (
                        <p className="text-white/65 text-[11px]">
                          Следующее списание: {new Date(subscriptionNextChargeAt).toLocaleDateString('ru-RU')}
                        </p>
                      ) : null}
                      {subscriptionEndDate ? (
                        <p className="text-white/75 text-xs">
                          Доступ до {new Date(subscriptionEndDate).toLocaleDateString('ru-RU')}
                        </p>
                      ) : null}
                      {subscriptionNextChargeAt && !isCanceled ? (
                        <>
                          <label className="flex items-start gap-2 text-white/80 text-[11px]">
                            <input
                              type="checkbox"
                              className="mt-0.5 h-4 w-4 accent-amber-400"
                              checked={cancelConfirmed}
                              onChange={(e) => setCancelConfirmed(Boolean(e.target.checked))}
                            />
                            <span>Я хочу отменить автопродление</span>
                          </label>
                          <Button
                            size="md"
                            variant="ghost"
                            className="w-full"
                            disabled={Boolean(loadingType) || isCanceled || !cancelConfirmed}
                            onClick={cancelSubscription}
                          >
                            {isCanceled ? 'Автопродление отменено' : (loadingType === 'cancel' ? 'Отменяю...' : 'Отменить автопродление')}
                          </Button>
                        </>
                      ) : null}
                      <p className="text-white/55 text-[11px] text-center pt-1">
                        <button type="button" className="text-amber-300/90 underline-offset-2 hover:underline" onClick={(e) => { e.preventDefault(); e.stopPropagation(); setShowOfferModal(true); }}>
                          Публичная оферта
                        </button>
                        {' · '}
                        <button type="button" className="text-amber-300/90 underline-offset-2 hover:underline" onClick={(e) => { e.preventDefault(); e.stopPropagation(); setShowAgreementModal(true); }}>
                          Пользовательское соглашение
                        </button>
                      </p>
                    </div>
                    <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-3 space-y-3">
                      <p className="text-amber-200/90 text-[11px] font-medium">Продлите тариф VIP</p>
                      <div className="grid grid-cols-1 gap-3">
                        {[
                          { id: 'vip_10d', oldPrice: 599, price: 199, period: 'доступ на 10 дней' },
                          { id: 'vip_30d', oldPrice: 999, price: 399, period: 'доступ на 30 дней' },
                          { id: 'vip_100d', oldPrice: 2999, price: 999, period: 'доступ на 100 дней' },
                        ].map((opt) => (
                          <button
                            key={opt.id}
                            type="button"
                            className={VIP_TIER_CHOICE_BUTTON_CLASS}
                            onClick={() => createPayment(opt.id)}
                            disabled={Boolean(loadingType)}
                          >
                            <span className="text-white/90 text-sm">
                              <span className="line-through text-white/45 mr-1">{opt.oldPrice} ₽</span>
                              <span className="text-amber-300 font-medium">{opt.price} ₽</span>
                              <span className="text-white/70 text-xs ml-1"> · {opt.period}</span>
                            </span>
                            {loadingType === opt.id ? (
                              <span className="text-amber-200 text-xs">...</span>
                            ) : null}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                ) : hasSubscriptionUi && tab === 'vip' ? (
                  <div className="mt-3 rounded-2xl border border-amber-500/30 bg-amber-500/10 p-3 space-y-3">
                    <p className="text-emerald-300 text-[13px] font-semibold">
                      Безлимитный доступ ко всем функциям приложения.
                    </p>
                    <div className="grid grid-cols-1 gap-3">
                      {[
                        { id: 'vip_10d', oldPrice: 599, price: 199, period: 'доступ на 10 дней' },
                        { id: 'vip_30d', oldPrice: 999, price: 399, period: 'доступ на 30 дней' },
                        { id: 'vip_100d', oldPrice: 2999, price: 999, period: 'доступ на 100 дней' },
                      ].map((opt) => (
                        <button
                          key={opt.id}
                          type="button"
                          className={VIP_TIER_CHOICE_BUTTON_CLASS}
                          onClick={() => createPayment(opt.id)}
                          disabled={Boolean(loadingType) || !agreementAccepted}
                        >
                          <span className="text-white/90 text-sm">
                            <span className="line-through text-white/45 mr-1">{opt.oldPrice} ₽</span>
                            <span className="text-amber-300 font-medium">{opt.price} ₽</span>
                            <span className="text-white/70 text-xs ml-1"> · {opt.period}</span>
                          </span>
                          {loadingType === opt.id ? (
                            <span className="text-amber-200 text-xs">...</span>
                          ) : null}
                        </button>
                      ))}
                    </div>
                    <label className="flex items-start gap-2 text-white/80 text-[11px]">
                      <input
                        type="checkbox"
                        className="mt-0.5 h-4 w-4 accent-amber-400"
                        checked={agreementAccepted}
                        onChange={(e) => setAgreementAccepted(Boolean(e.target.checked))}
                      />
                      <span>
                        Я принимаю условия{' '}
                        <button type="button" className="text-amber-300 underline-offset-2 hover:underline" onClick={(e) => { e.preventDefault(); e.stopPropagation(); setShowOfferModal(true); }}>
                          Публичной оферты
                        </button>
                        {' и '}
                        <button type="button" className="text-amber-300 underline-offset-2 hover:underline" onClick={(e) => { e.preventDefault(); e.stopPropagation(); setShowAgreementModal(true); }}>
                          Пользовательского соглашения
                        </button>
                      </span>
                    </label>
                  </div>
                ) : null}

                {tab === 'balance' && !hasActivePayment ? (
                  <div className="mt-3 rounded-2xl border border-white/10 bg-white/[0.03] p-3 space-y-2">
                    <p className="text-white/80 text-[13px] mb-3">Текущий баланс: <span className="text-amber-300">{formatStars(balanceCents)}</span></p>
                    <div className="grid grid-cols-3 gap-2 mb-6">
                      {TOPUP_OPTIONS.map((value) => (
                        <button
                          key={value}
                          type="button"
                          className={`w-full rounded-xl border px-3 py-2 text-sm transition ${
                            selectedTopup === value
                              ? 'border-amber-400/60 bg-amber-300/15 text-amber-200'
                              : 'border-white/15 bg-black/20 text-white/75'
                          }`}
                          onClick={() => setSelectedTopup(value)}
                        >
                          +{value} ₽
                        </button>
                      ))}
                    </div>
                    <div className="h-3" />
                    <label className="flex items-start gap-4 text-white/80 text-[11px]">
                      <input
                        type="checkbox"
                        className="mt-0.5 h-4 w-4 accent-amber-400"
                        checked={agreementAccepted}
                        onChange={(e) => setAgreementAccepted(Boolean(e.target.checked))}
                      />
                      <span>
                        Я принимаю условия{' '}
                        <button type="button" className="text-amber-300" onClick={() => setShowAgreementModal(true)}>
                          Пользовательского соглашения
                        </button>
                        {' и '}
                        <button type="button" className="text-amber-300" onClick={() => setShowTariffModal(true)}>
                          тарифов использования
                        </button>
                      </span>
                    </label>
                    <Button
                      size="md"
                      className="w-full mt-1"
                      disabled={Boolean(loadingType) || !agreementAccepted}
                      onClick={() => createPayment('topup', selectedTopup)}
                    >
                      {loadingType === `topup_${selectedTopup}` ? 'Открываю форму оплаты...' : 'Пополнить баланс'}
                    </Button>
                  </div>
                ) : null}
              </>
            ) : null}

            {!checkoutToken && showSupportView ? (
              <div className="mt-3 rounded-2xl border border-white/10 bg-white/[0.03] p-3 space-y-3">
                <p className="text-white/80 text-xs">Напишите нам ваш вопрос, ошибку или предложение.</p>
                <textarea
                  value={supportMessage}
                  onChange={(e) => setSupportMessage(e.target.value)}
                  rows={5}
                  placeholder="Опишите обращение..."
                  className="w-full rounded-xl border border-white/15 bg-black/30 p-3 text-sm text-white/90 outline-none focus:border-amber-400/50"
                />
                <div className="space-y-1">
                  <label className="text-white/70 text-xs">Изображение (до 2 МБ)</label>
                  <input
                    type="file"
                    accept="image/png,image/jpeg,image/webp"
                    onChange={(e) => {
                      const file = e.target.files?.[0] || null;
                      setSupportImage(file);
                    }}
                    className="w-full text-xs text-white/70 file:mr-3 file:rounded-lg file:border file:border-amber-400/40 file:bg-amber-300/10 file:px-3 file:py-1 file:text-amber-200"
                  />
                  {supportImage ? (
                    <p className="text-[11px] text-white/55">
                      Выбрано: {supportImage.name} ({Math.ceil(supportImage.size / 1024)} КБ)
                    </p>
                  ) : null}
                </div>
                <Button size="md" className="w-full" disabled={supportSending} onClick={sendSupportAppeal}>
                  {supportSending ? 'Отправляю...' : 'Отправить обращение'}
                </Button>
                {supportSuccess ? <p className="text-emerald-300 text-xs">{supportSuccess}</p> : null}
              </div>
            ) : null}

            {error ? <p className="text-rose-300 text-xs mt-2">{typeof error === 'string' ? error : String(error?.message ?? error ?? 'Ошибка')}</p> : null}
            <Button size="md" variant="ghost" className="w-full mt-3" onClick={handleClose}>
              Закрыть
            </Button>
          </motion.div>
        </motion.div>
      ) : null}
      <AnimatePresence>
        {open && showTariffModal ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[95] flex items-center justify-center p-3"
            style={{
              paddingTop: 'calc(env(safe-area-inset-top) + 2rem)',
              paddingBottom: 'calc(env(safe-area-inset-bottom) + 4rem)',
            }}
          >
            <div
              className="absolute inset-0 bg-black/80 backdrop-blur-sm"
              onClick={() => setShowTariffModal(false)}
              aria-hidden
            />
            <motion.div
              initial={{ y: 18, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: 18, opacity: 0 }}
              className="relative z-10 w-full max-w-lg rounded-3xl border border-amber-500/30 bg-[#0b0b1e] p-4"
              style={{ maxHeight: 'calc(100dvh - env(safe-area-inset-top) - env(safe-area-inset-bottom) - 7rem)' }}
            >
              <p className="text-amber-300 text-sm">Тарифы использования</p>
              <div className="mt-2 max-h-[52dvh] overflow-y-auto whitespace-pre-wrap text-white/70 text-[11px] leading-relaxed scrollbar-hide">
                {TARIFF_TEXT}
              </div>
              <Button size="md" variant="ghost" className="w-full mt-3" onClick={() => setShowTariffModal(false)}>
                Закрыть
              </Button>
            </motion.div>
          </motion.div>
        ) : null}
      </AnimatePresence>
      <AnimatePresence>
        {open && showAgreementModal ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[95] flex items-center justify-center p-3"
            style={{
              paddingTop: 'calc(env(safe-area-inset-top) + 2rem)',
              paddingBottom: 'calc(env(safe-area-inset-bottom) + 4rem)',
            }}
          >
            <div
              className="absolute inset-0 bg-black/80 backdrop-blur-sm"
              onClick={() => setShowAgreementModal(false)}
              aria-hidden
            />
            <motion.div
              initial={{ y: 18, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: 18, opacity: 0 }}
              className="relative z-10 w-full max-w-lg rounded-3xl border border-amber-500/30 bg-[#0b0b1e] p-4"
              style={{ maxHeight: 'calc(100dvh - env(safe-area-inset-top) - env(safe-area-inset-bottom) - 7rem)' }}
            >
              <p className="text-amber-300 text-sm">Пользовательское соглашение</p>
              <div className="mt-2 max-h-[52dvh] overflow-y-auto whitespace-pre-wrap text-white/70 text-[11px] leading-relaxed scrollbar-hide">
                {agreementText}
              </div>
              <Button size="md" variant="ghost" className="w-full mt-3" onClick={() => setShowAgreementModal(false)}>
                Закрыть
              </Button>
            </motion.div>
          </motion.div>
        ) : null}
      </AnimatePresence>
      <AnimatePresence>
        {open && showOfferModal ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[95] flex items-center justify-center p-3"
            style={{
              paddingTop: 'calc(env(safe-area-inset-top) + 2rem)',
              paddingBottom: 'calc(env(safe-area-inset-bottom) + 4rem)',
            }}
          >
            <div
              className="absolute inset-0 bg-black/80 backdrop-blur-sm"
              onClick={() => setShowOfferModal(false)}
              aria-hidden
            />
            <motion.div
              initial={{ y: 18, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: 18, opacity: 0 }}
              className="relative z-10 w-full max-w-lg rounded-3xl border border-amber-500/30 bg-[#0b0b1e] p-4"
              style={{ maxHeight: 'calc(100dvh - env(safe-area-inset-top) - env(safe-area-inset-bottom) - 7rem)' }}
            >
              <p className="text-amber-300 text-sm">Публичная оферта</p>
              <div className="mt-2 max-h-[52dvh] overflow-y-auto whitespace-pre-wrap text-white/70 text-[11px] leading-relaxed scrollbar-hide">
                {VIP_TARIFF_OFFER_TEXT}
              </div>
              <Button size="md" variant="ghost" className="w-full mt-3" onClick={() => setShowOfferModal(false)}>
                Закрыть
              </Button>
            </motion.div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </AnimatePresence>
  );
}
