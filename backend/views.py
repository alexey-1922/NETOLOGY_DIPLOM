from distutils.util import strtobool

from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password

from django.db import IntegrityError
from django.db.models import Q, Sum, F
from django.http import JsonResponse
from django.views.generic import TemplateView
from rest_framework import status

from rest_framework.authtoken.models import Token
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView
from ujson import loads as load_json

from backend.models import Shop, Category, ProductInfo, Order, OrderItem, Contact, ConfirmEmailToken
from backend.serializers import UserSerializer, CategorySerializer, ShopSerializer, ProductInfoSerializer, \
    OrderItemSerializer, OrderSerializer, ContactSerializer
from backend.signals import new_order

from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiParameter


class RegisterAccount(APIView):
    """
    Для регистрации покупателей
    """
    @extend_schema(summary="Регистрация покупателей",
        request=UserSerializer,
        responses={
            201: {'example': {'Status': True, 'Comment': 'Пользователь зарегистрирован'}},
            400: {'example': {'Status': False, 'Error': 'Не указаны все необходимые аргументы'}},
            403: {'example': {'Status': False, 'Error': 'Отказано в доступе'}}
        }
    )
    # Регистрация методом POST
    def post(self, request, *args, **kwargs):

        # проверяем обязательные аргументы
        if {'first_name', 'last_name', 'email', 'password', 'company', 'position'}.issubset(request.data):
            try:
                validate_password(request.data['password'])
            except Exception as password_error:
                error_array = []
                for item in password_error:
                    error_array.append(item)
                return JsonResponse({'Status': False, 'Errors': {'password': error_array}})
            else:
                # проверяем данные для уникальности имени пользователя
                request.data._mutable = True
                request.data.update({})
                user_serializer = UserSerializer(data=request.data)
                if user_serializer.is_valid():
                    # сохраняем пользователя
                    user = user_serializer.save()
                    user.set_password(request.data['password'])
                    user.save()
                    token, _ = ConfirmEmailToken.objects.get_or_create(user_id=user.id)
                    send_email.delay('Подтверждение регистрации', f'Токен для подтверждения {token.key}',
                                     user.email)
                    return JsonResponse({'Status': True, 'Token for email confirmation': token.key},
                                        status=status.HTTP_201_CREATED)
                else:
                    return JsonResponse({'Status': False, 'Errors': user_serializer.errors},
                                        status=status.HTTP_403_FORBIDDEN)

        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'},
                            status=status.HTTP_400_BAD_REQUEST)


class ConfirmAccount(APIView):
    """
    Класс для подтверждения почтового адреса
    """

    throttle_classes = (AnonRateThrottle,)
    
    @extend_schema(summary="Подтверждение токена и email",
        request=UserSerializer,
        responses={
            200: {'example': {'Status': True, 'Comment': 'Токен правильный'}},
            401: {'example': {'Status': False, 'Errors': 'Неправильно указан токен или email'}},
            400: {'example': {'Status': False, 'Error': 'Не указаны все необходимые аргументы'}}
        }
    )

    # Регистрация методом POST
    def post(self, request, *args, **kwargs):

        # проверяем обязательные аргументы
        if {'email', 'token'}.issubset(request.data):

            token = ConfirmEmailToken.objects.filter(user__email=request.data['email'],
                                                     key=request.data['token']).first()
            if token:
                token.user.is_active = True
                token.user.save()
                token.delete()
                return JsonResponse({'Status': True})
            else:
                return JsonResponse({'Status': False, 'Errors': 'Неправильно указан токен или email'})

        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})


class AccountDetails(APIView):
    """
    Класс для работы данными пользователя
    """

    throttle_classes = (UserRateThrottle,)
    
    @extend_schema(summary="Получение данных о пользователе",
        request=UserSerializer,
        responses={
            200: {'example': {
                "id": 1,
                "first_name": "Сергей",
                "last_name": "Петров",
                "email": "petrov-s@gmail.com",
                "company": "АО РДУ",
                "position": "инженер КИП",
                "contacts": "+79998887777"       
            }
            },
            403: {'example': {'Status': False, 'Comment': 'Error', 'Error': 'Требуется вход в систему'}},
        }
    )

    # получить данные
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=status.HTTP_403_FORBIDDEN)

        serializer = UserSerializer(request.user)
        return Response(serializer.data)


    @extend_schema(summary="Редактирование данных о пользователе",
        request=UserSerializer,
        responses={
            201: {'example': {'Status': True, 'Comment': 'Пользователь обновлен'}},
            400: {'example': {'Status': False, 'Error': 'Недостаточно сложный пароль'}},
            403: {'example': {'Status': False, 'Error': 'Требуется вход в систему'}}
        }
    )
    # Редактирование методом POST
    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'},
                                status=status.HTTP_403_FORBIDDEN)
        # проверяем обязательные аргументы

        if 'password' in request.data:
            errors = {}
            # проверяем пароль на сложность
            try:
                validate_password(request.data['password'])
            except Exception as password_error:
                error_array = []
                # noinspection PyTypeChecker
                for item in password_error:
                    error_array.append(item)
                return JsonResponse({'Status': False, 'Errors': {'password': error_array}},
                                    status=status.HTTP_400_BAD_REQUEST)
            else:
                request.user.set_password(request.data['password'])

        # проверяем остальные данные
        user_serializer = UserSerializer(request.user, data=request.data, partial=True)
        if user_serializer.is_valid():
            user_serializer.save()
            return JsonResponse({'Status': True}, status=status.HTTP_200_OK)
        else:
            return JsonResponse({'Status': False, 'Errors': user_serializer.errors},
                                status=status.HTTP_400_BAD_REQUEST)


class LoginAccount(APIView):
    """
    Класс для авторизации пользователей
    """

    throttle_classes = (AnonRateThrottle,)
    
    @extend_schema(summary="Авторизация пользователя",
        request=UserSerializer,
        responses={
            201: {'example': {'Status': True, 'Comment': 'Вы вошли в систему'}},
            400: {'example': {'Status': False, 'Error': 'Не указаны все необходимые аргументы'}},
            403: {'example': {'Status': False, 'Error': 'Не удалось авторизовать'}}
        }
    )

    # Авторизация методом POST
    def post(self, request, *args, **kwargs):

        if {'email', 'password'}.issubset(request.data):
            user = authenticate(request, username=request.data['email'], password=request.data['password'])

            if user is not None:
                if user.is_active:
                    token, _ = Token.objects.get_or_create(user=user)

                    return JsonResponse({'Status': True, 'Token': token.key})

            return JsonResponse({'Status': False, 'Errors': 'Не удалось авторизовать'},
                                status=status.HTTP_403_FORBIDDEN)

        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'},
                            status=status.HTTP_400_BAD_REQUEST)


class CategoryView(ListAPIView):
    """
    Класс для просмотра категорий
    """
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class ShopView(ListAPIView):
    """
    Класс для просмотра списка магазинов
    """
    queryset = Shop.objects.filter(state=True)
    serializer_class = ShopSerializer


class ProductInfoView(APIView):
    """
    Класс для поиска товаров
    """

    throttle_classes = (AnonRateThrottle,)
    
    @extend_schema(summary="Поиск товара",
        request=ProductInfoSerializer,
        responses={
            200: {'example': {
                "id": 4216292,
                "model": "apple/iphone/xs-max",
                "product": "phone",
                "shop": "petrov-s@gmail.com",
                "quantity": 14,
                "price": 110000,
                "price_rrc": 116190,
                "product_parameters": [
                    {
                        "Диагональ (дюйм)": 6.1,
                        "Разрешение (пикс)": "1792x828",
                        "Встроенная память (Гб)": 256,
                        "Цвет": "черный"
                    }      
                ]
            },
        }
        }
    )

    def get(self, request, *args, **kwargs):

        query = Q(shop__state=True)
        shop_id = request.query_params.get('shop_id')
        category_id = request.query_params.get('category_id')

        if shop_id:
            query = query & Q(shop_id=shop_id)

        if category_id:
            query = query & Q(product__category_id=category_id)

        # фильтруем и отбрасываем дуликаты
        queryset = ProductInfo.objects.filter(
            query).select_related(
            'shop', 'product__category').prefetch_related(
            'product_parameters__parameter').distinct()

        serializer = ProductInfoSerializer(queryset, many=True)

        return Response(serializer.data)


class BasketView(APIView):
    """
    Класс для работы с корзиной пользователя
    """

    throttle_classes = (UserRateThrottle,)
    
    @extend_schema(summary="Получение корзины пользователя",
        request=OrderSerializer,
        responses={
            200: {'example': 
                {
                "id": 1,
                "ordered_items": [
                    {
                        "order":1,
                        "product_info": [
                            {
                                "name": "Смартфон Apple iPhone XS Max 512GB (золотистый)",
                                "model": "apple/iphone/xs-max",
                                "external_id": 1,
                                "product": "phone",
                                "shop": "Связной",
                                "quantity": 1,
                                "price": 110000,
                                "price_rcc": 116990
                                }],
                        "shop": "Связной",
                        "quantity": "1"}],
                        "state": "basket",
                        "dt": "11.03.2023",
                        "total_sum": 1,
                        "contact": "Петров Сергей"
                },
        },
        403: {'example': {'Status': False, 'Comment': 'Error', 'Error': 'Требуется вход в систему'}},
        }
    )

    # получить корзину
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'},
                                status=status.HTTP_403_FORBIDDEN)
        basket = Order.objects.filter(
            user_id=request.user.id, state='basket').prefetch_related(
            'ordered_items__product_info__product__category',
            'ordered_items__product_info__product_parameters__parameter').annotate(
            total_sum=Sum(F('ordered_items__quantity') * F('ordered_items__product_info__price'))).distinct()

        serializer = OrderSerializer(basket, many=True)
        return Response(serializer.data)


    @extend_schema(summary="Редактирование корзины пользователя",
        request=OrderItemSerializer,
        responses={
            201: {'example': {'Status': True, 'Comment': "Объект создан"}},
            400: {'example': {'Status': False, 'Error': 'Не верный формат запроса'}},
            403: {'example': {'Status': False, 'Error': 'Требуется вход в систему'}},
        }
    )
    # редактировать корзину
    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'},
                                status=status.HTTP_403_FORBIDDEN)

        items_sting = request.data.get('items')
        if items_sting:
            try:
                items_dict = load_json(items_sting)
            except ValueError:
                JsonResponse({'Status': False, 'Errors': 'Неверный формат запроса'})
            else:
                basket, _ = Order.objects.get_or_create(user_id=request.user.id, state='basket')
                objects_created = 0
                for order_item in items_dict:
                    order_item.update({'order': basket.id})
                    serializer = OrderItemSerializer(data=order_item)
                    if serializer.is_valid():
                        try:
                            serializer.save()
                        except IntegrityError as error:
                            return JsonResponse({'Status': False, 'Errors': str(error)})
                        else:
                            objects_created += 1

                    else:

                        JsonResponse({'Status': False, 'Errors': serializer.errors})

                return JsonResponse({'Status': True, 'Создано объектов': objects_created},
                                    status.HTTP_201_CREATED)
        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'},
                            status.HTTP_400_BAD_REQUEST)

    @extend_schema(summary="Удаление товаров из корзины пользователя",
        request=OrderItemSerializer,
        responses={
            200: {'example': {'Status': True, 'Comment': "Объект удален"}},
            400: {'example': {'Status': False, 'Error': 'Не верный формат запроса'}},
            403: {'example': {'Status': False, 'Error': 'Требуется вход в систему'}},
        }
    )

    # удалить товары из корзины
    def delete(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        items_sting = request.data.get('items')
        if items_sting:
            items_list = items_sting.split(',')
            basket, _ = Order.objects.get_or_create(user_id=request.user.id, state='basket')
            query = Q()
            objects_deleted = False
            for order_item_id in items_list:
                if order_item_id.isdigit():
                    query = query | Q(order_id=basket.id, id=order_item_id)
                    objects_deleted = True

            if objects_deleted:
                deleted_count = OrderItem.objects.filter(query).delete()[0]
                return JsonResponse({'Status': True, 'Удалено объектов': deleted_count},
                                    status=status.HTTP_200_OK)
        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'},
                            status.HTTP_400_BAD_REQUEST)

    @extend_schema(summary="Добавить позиции в корзину пользователя",
        request=OrderItemSerializer,
        responses={
            200: {'example': {'Status': True, 'Comment': "Объект обновлен"}},
            400: {'example': {'Status': False, 'Error': 'Не верный формат запроса'}},
            403: {'example': {'Status': False, 'Error': 'Требуется вход в систему'}},
        }
    )

    # добавить позиции в корзину
    def put(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        items_sting = request.data.get('items')
        if items_sting:
            try:
                items_dict = load_json(items_sting)
            except ValueError:
                JsonResponse({'Status': False, 'Errors': 'Неверный формат запроса'})
            else:
                basket, _ = Order.objects.get_or_create(user_id=request.user.id, state='basket')
                objects_updated = 0
                for order_item in items_dict:
                    if type(order_item['id']) == int and type(order_item['quantity']) == int:
                        objects_updated += OrderItem.objects.filter(order_id=basket.id, id=order_item['id']).update(
                            quantity=order_item['quantity'])

                return JsonResponse({'Status': True, 'Обновлено объектов': objects_updated},
                                    status=status.HTTP_200_OK)
        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'},
                            status.HTTP_400_BAD_REQUEST)


class PartnerUpdate(APIView):
    """
    Класс для обновления прайса от поставщика
    """

    throttle_classes = (UserRateThrottle,)
    
    @extend_schema(summary="Обновление прайса поставщика",
        responses={
            200: {'example': {'Status': True, 'Comment': 'Прайс обновлен'}},
            403: {'example': {'Status': False, 'Error': 'Только для магазинов'}},
            400: {'example': {'Status': False, 'Error': 'Не верный формат запроса'}}
        }
    )

    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'},
                                status=status.HTTP_403_FORBIDDEN)

        if request.user.type != 'shop':
            return JsonResponse({'Status': False, 'Error': 'For shops only'},
                                status=status.HTTP_403_FORBIDDEN)

        url = request.data.get('url')
        if url:
            try:
                task = get_import.delay(url, request.user.id)
            except IntegrityError as e:
                return JsonResponse({'Status': False,
                                     'Errors': f'Integrity Error: {e}'})

            return JsonResponse({'Status': True}, status=status.HTTP_200_OK)

        return JsonResponse({'Status': False, 'Errors': 'All necessary arguments are not specified'},
                            status=status.HTTP_400_BAD_REQUEST)


class PartnerState(APIView):
    """
    Класс для работы со статусом поставщика
    """

    throttle_classes = (UserRateThrottle,)

    @extend_schema(summary="Получить статус поставщика",
        request=ShopSerializer,
        responses={
            200: {'example': 
                {
                "id": 1,
                "name": "Связной",
                "state": True,
                },
        },
        403: {'example': {'Status': False, 'Comment': 'Error', 'Error': 'Требуется вход в систему'}},
        403: {'example': {'Status': False, 'Comment': 'Error', 'Error': 'Только для магазинов'}},
        }
    )


    # получить текущий статус
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'},
                                status=status.HTTP_403_FORBIDDEN)

        if request.user.type != 'shop':
            return JsonResponse({'Status': False, 'Error': 'Только для магазинов'},
                                status=status.HTTP_403_FORBIDDEN)

        shop = request.user.shop
        serializer = ShopSerializer(shop)
        return Response(serializer.data)
    
    @extend_schema(summary="Изменить статус поставщика",
        responses={
            200: {'example': {'Status': True, 'Comment': 'Текущий статус изменен'}},
            403: {'example': {'Status': False, 'Error': 'Только для магазинов'}},
            403: {'example': {'Status': False, 'Error': 'Требуется вход в систему'}},
            400: {'example': {'Status': False, 'Error': 'Не верный формат запроса'}}
        }
    )

    # изменить текущий статус
    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'},
                                status=status.HTTP_403_FORBIDDEN)

        if request.user.type != 'shop':
            return JsonResponse({'Status': False, 'Error': 'Только для магазинов'},
                                status=status.HTTP_403_FORBIDDEN)
        state = request.data.get('state')
        if state:
            try:
                Shop.objects.filter(user_id=request.user.id).update(state=strtobool(state))
                return JsonResponse({'Status': True}, status=status.HTTP_200_OK)
            except ValueError as error:
                return JsonResponse({'Status': False, 'Errors': str(error)})

        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'},
                            status=status.HTTP_400_BAD_REQUEST)


class PartnerOrders(APIView):
    """
    Класс для получения заказов поставщиками
    """

    throttle_classes = (UserRateThrottle,)
    
    @extend_schema(summary="Получить заказ поставщика",
        request=OrderSerializer,
        responses={
            200: {'example': 
                {
                "id": 1,
                "ordered_items": [
                    {
                        "order":1,
                        "product_info": [
                            {
                                "name": "Смартфон Apple iPhone XS Max 512GB (золотистый)",
                                "model": "apple/iphone/xs-max",
                                "external_id": 1,
                                "product": "phone",
                                "shop": "Связной",
                                "quantity": 1,
                                "price": 110000,
                                "price_rcc": 116990
                                }],
                        "shop": "Связной",
                        "quantity": "1"}],
                        "dt": "11.03.2023",
                        "total_sum": 1,
                },
        },
        403: {'example': {'Status': False, 'Comment': 'Error', 'Error': 'Требуется вход в систему'}},
        403: {'example': {'Status': False, 'Comment': 'Error', 'Error': 'Только для маазинов'}},
        }
    )
    


    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'},
                                status=status.HTTP_403_FORBIDDEN)

        if request.user.type != 'shop':
            return JsonResponse({'Status': False, 'Error': 'Только для магазинов'},
                                status=status.HTTP_403_FORBIDDEN)

        order = Order.objects.filter(
            ordered_items__product_info__shop__user_id=request.user.id).exclude(state='basket').prefetch_related(
            'ordered_items__product_info__product__category',
            'ordered_items__product_info__product_parameters__parameter').select_related('contact').annotate(
            total_sum=Sum(F('ordered_items__quantity') * F('ordered_items__product_info__price'))).distinct()

        serializer = OrderSerializer(order, many=True)
        return Response(serializer.data)


class ContactView(APIView):
    """
    Класс для работы с контактами покупателей
    """

    throttle_classes = (UserRateThrottle,)
    
    @extend_schema(summary="Получить свои контакты",
        request=ContactSerializer,
        responses={
            200: {'example': {
                "id": 1,
                "country": "РФ",
                "zip": 197228,
                "city": "Санкт-Петербург",
                "street": "Ивинская",
                "house": 13,
                "structure": "+79998887777",
                "building": "",
                "apartment": "",
                "user": "admin",
                "phone": "+79998887777"     
            }
            },
            403: {'example': {'Status': False, 'Comment': 'Error', 'Error': 'Требуется вход в систему'}},
        }
    ) 

    # получить мои контакты
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'},
                                status=status.HTTP_403_FORBIDDEN)
        contact = Contact.objects.filter(
            user_id=request.user.id)
        serializer = ContactSerializer(contact, many=True)
        return Response(serializer.data)

    @extend_schema(summary="Добавить новый контакт",
        request=ContactSerializer,
        responses={
            201: {'example': {'Status': True, 'Comment': "Контак создан"}},
            400: {'example': {'Status': False, 'Error': 'Не верный формат запроса'}},
            401: {'example': {'Status': False, 'Error': 'Не указаны все необходимые аргументы'}},
            403: {'example': {'Status': False, 'Error': 'Требуется вход в систему'}},
        }
    )

    # добавить новый контакт
    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'},
                                status=status.HTTP_403_FORBIDDEN)

        if {'city', 'street', 'phone'}.issubset(request.data):
            request.data._mutable = True
            request.data.update({'user': request.user.id})
            serializer = ContactSerializer(data=request.data)

            if serializer.is_valid():
                serializer.save()
                return JsonResponse({'Status': True}, status=status.HTTP_201_CREATED)
            else:
                JsonResponse({'Status': False, 'Errors': serializer.errors},
                             status=status.HTTP_400_BAD_REQUEST)

        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'},
                            status=status.HTTP_401_UNAUTHORIZED)

    @extend_schema(summary="Удалить контакт",
        request=ContactSerializer,
        responses={
            200: {'example': {'Status': True, 'Comment': "Объект удален"}},
            400: {'example': {'Status': False, 'Error': 'Не указаны все необходимые аргументы'}},
            403: {'example': {'Status': False, 'Error': 'Требуется вход в систему'}},
        }
    )

    # удалить контакт
    def delete(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'},
                                status=status.HTTP_403_FORBIDDEN)

        items_sting = request.data.get('items')
        if items_sting:
            items_list = items_sting.split(',')
            query = Q()
            objects_deleted = False
            for contact_id in items_list:
                if contact_id.isdigit():
                    query = query | Q(user_id=request.user.id, id=contact_id)
                    objects_deleted = True

            if objects_deleted:
                deleted_count = Contact.objects.filter(query).delete()[0]
                return JsonResponse({'Status': True, 'Удалено объектов': deleted_count},
                                    status=status.HTTP_200_OK)
        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'},
                            status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(summary="Редактировать контакт",
        request=ContactSerializer,
        responses={
            200: {'example': {'Status': True, 'Comment': "Объект обновлен"}},
            400: {'example': {'Status': False, 'Error': 'Не указаны все необходимые аргументы'}},
            403: {'example': {'Status': False, 'Error': 'Требуется вход в систему'}},
        }
    )

    # редактировать контакт
    def put(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'},
                                status=status.HTTP_403_FORBIDDEN)

        if 'id' in request.data:
            if request.data['id'].isdigit():
                contact = Contact.objects.filter(id=request.data['id'], user_id=request.user.id).first()
                print(contact)
                if contact:
                    serializer = ContactSerializer(contact, data=request.data, partial=True)
                    if serializer.is_valid():
                        serializer.save()
                        return JsonResponse({'Status': True}, status=status.HTTP_200_OK)
                    else:
                        JsonResponse({'Status': False, 'Errors': serializer.errors},
                                     status=status.HTTP_400_BAD_REQUEST)

        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'},
                            status=status.HTTP_400_BAD_REQUEST)


class OrderView(APIView):
    """
    Класс для получения и размешения заказов пользователями
    """

    throttle_classes = (UserRateThrottle,)

    @extend_schema(summary="Получить мои заказы",
        request=OrderSerializer,
        responses={
            200: {'example': 
                {
                "id": 1,
                "ordered_items": [
                    {
                        "order":1,
                        "product_info": [
                            {
                                "name": "Смартфон Apple iPhone XS Max 512GB (золотистый)",
                                "model": "apple/iphone/xs-max",
                                "external_id": 1,
                                "product": "phone",
                                "shop": "Связной",
                                "quantity": 1,
                                "price": 110000,
                                "price_rcc": 116990
                                }],
                        "shop": "Связной",
                        "quantity": "1"}],
                        "dt": "11.03.2023",
                        "total_sum": 1,
                },
        },
        403: {'example': {'Status': False, 'Comment': 'Error', 'Error': 'Требуется вход в систему'}},
        }
    )

    # получить мои заказы
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'},
                                status=status.HTTP_403_FORBIDDEN)
        order = Order.objects.filter(
            user_id=request.user.id).exclude(state='basket').prefetch_related(
            'ordered_items__product_info__product__category',
            'ordered_items__product_info__product_parameters__parameter').select_related('contact').annotate(
            total_sum=Sum(F('ordered_items__quantity') * F('ordered_items__product_info__price'))).distinct()

        serializer = OrderSerializer(order, many=True)
        return Response(serializer.data)

    @extend_schema(summary="Разместить заказ из корзины",
        request=OrderSerializer,
        responses={
            200: {'example': {'Status': True, 'Comment': "Заказ размещен"}},
            400: {'example': {'Status': False, 'Error': 'Не указаны все необходимые аргументы'}},
            403: {'example': {'Status': False, 'Error': 'Требуется вход в систему'}},
        }
    )

    # разместить заказ из корзины
    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'},
                                status=status.HTTP_403_FORBIDDEN)

        if {'id', 'contact'}.issubset(request.data):
            if request.data['id'].isdigit():
                try:
                    is_updated = Order.objects.filter(
                        user_id=request.user.id, id=request.data['id']).update(
                        contact_id=request.data['contact'],
                        state='new')
                except IntegrityError as error:
                    print(error)
                    return JsonResponse({'Status': False, 'Errors': 'Неправильно указаны аргументы'},
                                        status=status.HTTP_400_BAD_REQUEST)
                else:
                    if is_updated:
                        new_order.send(sender=self.__class__, user_id=request.user.id)
                        return JsonResponse({'Status': True},
                                            status=status.HTTP_200_OK)

        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'},
                            status=status.HTTP_400_BAD_REQUEST)


class Home(TemplateView):
    template_name = 'home.html'
