from enum import Enum


class ServiceList(Enum):
    """Enum class for service list options."""

    OTHER = "Other"
    GENERAL = "General"
    AGENDA = "Agenda"
    STALL = "Stall_Sponsers"
    SCAN = "Scan"
    QUIZ = "quiz"
    QUIZ_DAY_1 = "quiz_day_1"
    QUIZ_DAY_2 = "quiz_day_2"
    QUIZ_DAY_3 = "quiz_day_3"  

    SL_AGENDA = "Agenda"
    SL_EXHIBITOR = "Exhibitors"
    SL_NAVIGATION = "Navigation"
    SL_OTHER = "Other"
