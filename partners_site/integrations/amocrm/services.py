from django.http import JsonResponse

from integrations.amocrm.exceptions import (
    ContactHasMultipleCustomersError,
    ContactHasNoCustomerError,
)
from orders.models import Order, OrderItem
from users.models import User

fields_ids = {
    'manager_id_field': 1506979, # Поле отв. менеджер
    'tg_id_field': 1104992, # Поле tg_id партнёра
    'status_id_field': 972634,
    'by_this_period_id_field': 1104934,
    'bonuses_id_field': 971580,
    'town_id_field': 972054,
    'full_price': 1105022,
    'pipeline_id': 1628622, #  7411865 - воронка тест 1628622 - воронка партнёры
    'tag_id': 610982,
    'need_help_tag': 607773,
    'status_id_order': 32809260, #  61586805 - статус переговоры 32809260 - статус новый заказ
    'status_id_kp': 39080307, # статус КП отправлено
    'chat_id': -4950490417,
    'catalog_id': 1682,
    'web_app_url': 'https://aleksslava.github.io/website.github.io/',
    'contacts_fields_id': {
        'tg_id_field': 1097296,
        'tg_username_field': 1097294,
        'max_id_field': 1105813
    },
    'lead_custom_fields': {
        'inn': 972566,
        'bik': 972568,
        'organization_adress': 1095240,
        'organization_account': 972570,
        'delivery_adress': 958756,
        'kard_pay': 1105338,
        'delivery_type': 971974,
        'discount_field': 972024,
        'partner_project_id': 938609,
        'appeal_type_field_id': 961948,
        'lead_target_field_id': 1103658,
        'need_manager_checkbox': 1105727,
    }
}

class CustomFiedsData:
    def __init__(self, order: Order, fields_id: dict):
        self.order = order
        self.fields_id = fields_id
        self.custom_fields = fields_id.get('lead_custom_fields')

    def get_discount(self): # Заполнение поля скидка в заказе

        discount_percent = self.order.order_discount_percent
        return str(discount_percent)

    def get_delivery_type(self):
        deliveryMethod = self.order.delivery_type
        if deliveryMethod == 'self_pickup':
            return 'ПВЗ (ХПИ)'
        else:
            return 'Доставка ТК'

    def get_discount_data(self):
        discount_value = self.get_discount()
        data = {
                    'field_id': self.custom_fields.get('discount_field'), # Поле скидки в сделке
                    'values': [
                        {
                            'value': discount_value
                        }]
                }
        return data

    def get_delivery_data(self):
        data = {"field_id": self.custom_fields.get('delivery_type'),  # Поле склад
                 "values": [
                     {"value": self.get_delivery_type()},
                 ]
                 }
        return data

    def get_delivery_adress_data(self):
        data = {"field_id": self.custom_fields.get('delivery_adress'),  # Поле адрес доставки
                 "values": [
                     {'enum_code': 'address_line_1',
                      'enum_id': 1,
                      'value': self.order.address.delivery_address_text}
                 ]
                 }
        return data

    def get_inn_data(self):
        inn_field_id = self.custom_fields.get('inn')
        inn_value = self.order.requisites.inn
        data = {"field_id": inn_field_id,  # Поле ИНН
                 "values": [
                     {"value": inn_value},
                 ]
                 }
        return data

    def get_bik_data(self):
        bik_field_id = self.custom_fields.get('bik')
        bik_value = self.order.requisites.bik
        data = {"field_id": bik_field_id,  # Поле Бик
                 "values": [
                     {"value": bik_value},
                 ]
                 }
        return data

    def get_organization_account_data(self):
        organization_account_field_id = self.custom_fields.get('organization_account')
        organization_account_value = self.order.requisites.settlement_account
        data = {"field_id": organization_account_field_id,  # Поле Р\с
                "values": [
                    {"value": organization_account_value},
                ]}
        return data

    def get_organization_adress_data(self):
        organization_adress_field_id = self.custom_fields.get('organization_adress')
        organization_adress_value = self.order.requisites.legal_address
        data = {"field_id": organization_adress_field_id,  # Поле юр. адрес
                 "values": [
                     {"value": organization_adress_value},
                 ]}
        return data

    def get_kard_pay_data(self):
        payment_type = self.order.payment_type
        if payment_type == 'card':
            flag = True
        else:
            flag = False
        data = {
                    'field_id': self.custom_fields.get('kard_pay'), # Чекбокс оплаты картой
                    'values': [
                        {
                            'value': flag
                        }
                    ]}
        return data

    def get_project_name_data(self):
        project_field_id = self.custom_fields.get('partner_project_id')
        data = {"field_id": project_field_id,  # Поле проект
                 "values": [
                     {"value": 'Выклы и УД (Партнеры)'},
                 ]
                 }
        return data

    def get_appeal_type(self):
        appeal_type_field_id = self.custom_fields.get('appeal_type_field_id')
        data = {"field_id": appeal_type_field_id,  # Поле обращение
                 "values": [
                     {"value": 'Повторное'},
                 ]
                 }
        return data

    def get_lead_target_data(self):
        lead_target_data = self.custom_fields.get('lead_target_field_id')
        data = {"field_id": lead_target_data,  # Поле проект
                 "values": [
                     {"value": 'Индивид. задача'},
                 ]
                 }
        return data

    def get_custom_fields_data(self):
        custom_fields_data = []
        if self.order.requisites is not None:
            custom_fields_data.append(self.get_inn_data())
            custom_fields_data.append(self.get_bik_data())
            custom_fields_data.append(self.get_organization_account_data())
            custom_fields_data.append(self.get_organization_adress_data())
        custom_fields_data.append(self.get_discount_data())
        custom_fields_data.append(self.get_delivery_data())
        custom_fields_data.append(self.get_delivery_adress_data())
        custom_fields_data.append(self.get_kard_pay_data())
        custom_fields_data.append(self.get_project_name_data())
        custom_fields_data.append(self.get_appeal_type())
        custom_fields_data.append(self.get_lead_target_data())
        return custom_fields_data

    def get_lead_tags(self):
        chat_bot_tag_id = self.fields_id.get('tag_id')
        tag_list = [chat_bot_tag_id]

        data = [{
            'id': value
        } for value in tag_list]
        return data


def create_data_for_lead(order: Order, user: User, fields_ids: dict) -> list:

    custom_fields_obj = CustomFiedsData(order, fields_ids)
    custom_fields_data = custom_fields_obj.get_custom_fields_data()
    tags_data = custom_fields_obj.get_lead_tags()

    data = [{
            'name': 'Заказ с магазина партнёров',
            'pipeline_id': fields_ids['pipeline_id'],
            'created_by': 0,
            'status_id': fields_ids['status_id_order'],
            'price': order.total,
            'responsible_user_id': 453498,
            'custom_fields_values': custom_fields_data,
            '_embedded': {
                'tags': tags_data,
                'contacts': [
                    {
                        'id': user.amo_id_contact
                    }
                ]
            }

        },]

    return data


def create_items_list(order_items: list[OrderItem]) -> list:
    catalog_id = 1682
    data = []
    for order_item in order_items:
        element_for_record = {
            'to_entity_id': order_item.product.amo_id,
            "to_entity_type": "catalog_elements",
            "metadata": {
                "quantity": order_item.qty,
                "catalog_id": catalog_id
            }
        }
        data.append(element_for_record)

    return data

def create_note_for_lead(order: Order, order_items: list[OrderItem]):
    text = 'Заказ с сайта партнёров:\n\n'
    text += 'Состав заказа:\n'
    for order_item in order_items:
        text += f'{order_item.product.name} - {order_item.qty}шт. по {order_item.current_unit_price_discounted} руб. - {order_item.bonuses_spent} бонусов списано = сумма {order_item.line_total}\n'

    text += f'Итого: {order.total}\n\n'
    text += f'Тип оплаты: {order.get_payment_type_display()}\n'
    if order.payment_type == 'invoice':
        text += (f'Инн: {order.requisites.inn}\n'
                 f'Адрес: {order.requisites.legal_address}\n'
                 f'Бик: {order.requisites.bik}\n'
                 f'Р\с: {order.requisites.settlement_account}\n\n')

    text += (f'Тип доставки: {order.get_delivery_type_display()}\n'
             f'Адрес доставки: {order.address.delivery_address_text}')

    return text


def get_customer_from_contact(response) -> int:
    contact_payload = response[1] if isinstance(response, tuple) and len(response) >= 2 else response

    if not isinstance(contact_payload, dict):
        raise ContactHasNoCustomerError()

    embedded = contact_payload.get('_embedded') or {}
    customers = embedded.get('customers') or []

    if not isinstance(customers, list):
        customers = []

    customer_ids = []
    for customer in customers:
        if not isinstance(customer, dict):
            continue
        customer_id = customer.get('id')
        if customer_id is not None:
            customer_ids.append(customer_id)

    if len(customer_ids) == 0:
        raise ContactHasNoCustomerError()

    if len(customer_ids) > 1:
        raise ContactHasMultipleCustomersError()

    return int(customer_ids[0])



