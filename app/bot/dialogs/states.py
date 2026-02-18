from aiogram.fsm.state import StatesGroup, State


class RegistrationSG(StatesGroup):
    full_name = State()
    phone = State()
    city = State()
    gender = State()
    waiting = State()
    confirm = State()


class MainMenuSG(StatesGroup):
    main = State()


class SubscriptionSG(StatesGroup):
    check = State()


class PaymentsSG(StatesGroup):
    main = State()


class RulesSG(StatesGroup):
    main = State()
    formatting = State()
    passability = State()


class ContactsSG(StatesGroup):
    main = State()


class ProfileSG(StatesGroup):
    main = State()
    history = State()


class ReferralsSG(StatesGroup):
    main = State()


class AdminSG(StatesGroup):
    main = State()
    export_users = State()
    user_lookup = State()
    user_tasks = State()
    import_tasks = State()
    global_stats = State()
    reports = State()
    analytics = State()
    users = State()
    manage = State()
    analytics_overview = State()
    analytics_dynamics = State()
    analytics_top = State()

    assigned_tasks = State()


class TasksSG(StatesGroup):
    empty = State()
    checking = State()

    choose_source = State()
    choose_gender = State()

    report_account = State()
    report_photo = State()
    report_success = State()

    review_list = State()
