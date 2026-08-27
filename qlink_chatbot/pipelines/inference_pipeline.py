from qlink_chatbot.pipelines.pipeline import Pipeline
from qlink_chatbot.processors.agenda_agent import AgendaAgent
from qlink_chatbot.processors.classifier import Classifier
from qlink_chatbot.processors.quiz import QuizAgent
from qlink_chatbot.processors.search_agent import SearchAgent
from qlink_chatbot.processors.service_list import ServiceList
from qlink_chatbot.processors.stall_sponser_agent import StallSponserAgent
from qlink_chatbot.processors.user_registration import (
    UserRegistration,
)
from qlink_chatbot.processors.scan_qr import ScanAgent


class InitialPipeline(Pipeline):
    """Pipeline class for inital user registartion and service list."""

    def __init__(self) -> None:
        processors = [UserRegistration(), Classifier(), ServiceList()]
        super().__init__(processors)


class GeneralPipeline(Pipeline):
    """Pipeline class for General Agent."""

    def __init__(self) -> None:
        processors = [SearchAgent()]
        super().__init__(processors)


class AgendaPipeline(Pipeline):
    """Pipeline class for Agenda Agent."""

    def __init__(self) -> None:
        processors = [AgendaAgent()]
        super().__init__(processors)


class StallSponserPipeline(Pipeline):
    """Pipeline class for Agenda Agent."""

    def __init__(self) -> None:
        processors = [StallSponserAgent()]
        super().__init__(processors)

class ScanQRPipeline(Pipeline):
    """Pipeline for Scan QR."""

    def __init__(self) -> None:
        processors = [ScanAgent()]
        super().__init__(processors)


class QuizPipeline(Pipeline):
    """Pipeline for Quiz."""

    def __init__(self) -> None:
        processors = [QuizAgent()]
        super().__init__(processors)