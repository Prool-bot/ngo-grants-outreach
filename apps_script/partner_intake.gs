/**
 * Run once in a private standalone Google Apps Script project, as the CRM owner.
 * Creates an unpublished opt-in form and a separate response spreadsheet.
 * No mail, no imported contacts, no automatic approval or public sharing.
 */
function createPartnerIntakeDraft() {
  const props = PropertiesService.getScriptProperties();
  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    if (props.getProperty('PARTNER_FORM_ID') || props.getProperty('PARTNER_RESPONSE_SHEET_ID')) {
      throw new Error('A draft or partial setup already exists. Inspect Script Properties and Drive; do not recreate automatically.');
    }
    const form = FormApp.create('NGO Grants — запит на партнерство', false);
    props.setProperty('PARTNER_FORM_ID', form.getId());
    form.setDescription('Чернетка. До публікації додайте повідомлення про обробку даних: відповідального, контакти, мету, строк зберігання та порядок відкликання згоди. Заповнення добровільне. Запит не означає підписки.');
    form.setPublishingSummary(false);
    form.setCollectEmail(true);
    form.setLimitOneResponsePerUser(true);
    form.setShowLinkToRespondAgain(false);
    form.setAllowResponseEdits(false);
    form.addTextItem().setTitle('Назва організації').setRequired(true);
    form.addTextItem().setTitle('Офіційний сайт (за наявності)').setRequired(false);
    form.addListItem().setTitle('Сфера діяльності').setChoiceValues([
      'Громадський сектор', 'Донори та фінансування', 'Освіта і наука', 'Культура та мистецтво',
      'Бізнес', 'Охорона здоров’я', 'Розвиток громад та інфраструктура', 'Інше'
    ]).setRequired(true);
    form.addCheckboxItem().setTitle('Цікавить').setChoiceValues([
      'Інформаційне партнерство', 'Рекламні послуги', 'Тематичний моніторинг грантів', 'Інше'
    ]).setRequired(true);
    form.addParagraphTextItem().setTitle('Ваш запит (не зазначайте конфіденційних даних)').setRequired(false);
    form.addCheckboxItem().setTitle('Необов’язкова згода на подальші пропозиції').setChoiceValues([
      'Погоджуюся отримувати електронною поштою комерційні пропозиції NGO Grants за обраними напрямами. Можу відкликати згоду в будь-який момент.'
    ]).setRequired(false);
    form.setConfirmationMessage('Дякуємо за запит. Він буде розглянутий окремо. Якщо Ви не погодилися на подальші пропозиції, Вас не додають до рекламної підписки.');
    const sheet = SpreadsheetApp.create('NGO Grants — приватні запити партнерів');
    props.setProperty('PARTNER_RESPONSE_SHEET_ID', sheet.getId());
    form.setDestination(FormApp.DestinationType.SPREADSHEET, sheet.getId());
    form.setPublished(false);
    console.log('Редагування форми: ' + form.getEditUrl());
    console.log('Приватний реєстр: ' + sheet.getUrl());
    console.log('Перед публікацією перевірте режим збирання email «Перевірені», права доступу та повідомлення про обробку даних. Не публікуйте реєстр.');
  } finally {
    lock.releaseLock();
  }
}
