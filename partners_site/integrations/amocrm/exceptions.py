class AmoCRMError(Exception):
    """Base exception for amoCRM integration errors."""


class ContactCustomerBindingError(AmoCRMError):
    """Base exception for contact-customer binding issues."""


class MultipleContactsError(AmoCRMError):
    def __init__(
        self,
        message: str = "Найдено более одного контакта, обратитесь к менеджеру",
    ):
        super().__init__(message)


class NotFoundTgIdContactError(AmoCRMError):
    def __init__(
        self,
        message: str = "Ни один контакт не привязан к Вашему телеграмм, обратитесь к менеджеру",
    ):
        super().__init__(message)

class NotFoundMaxIdContactError(AmoCRMError):
    def __init__(
        self,
        message: str = "Ни один контакт не привязан к Вашему MAX, обратитесь к менеджеру",
    ):
        super().__init__(message)


class ContactDoubleError(ContactCustomerBindingError):
    def __init__(
        self,
        message: str = "Найден повторяющийся номер телефона контакта, обратитесь к менеджеру",
    ):
        super().__init__(message)

class ContactHasNoCustomerError(ContactCustomerBindingError):
    def __init__(
        self,
        message: str = "Контакт не привязан к покупателю, обратитесь к менеджеру",
    ):
        super().__init__(message)


class ContactHasMultipleCustomersError(ContactCustomerBindingError):
    def __init__(
        self,
        message: str = "Контакт привязан к нескольким покупателям, обратитесь к менеджеру",
    ):
        super().__init__(message)


class CustomerNotFound(ContactCustomerBindingError):
    def __init__(
        self,
        message: str = "Не найден покупатель, обратитесь к менеджеру",
    ):
        super().__init__(message)


class AmoServerError(AmoCRMError):
    """Ошибка связи с сервером АМО"""
    def __init__(
        self,
        message: str = "Произошла ошибка связи с сервером, обратитесь к менеджеру",
    ):
        super().__init__(message)
