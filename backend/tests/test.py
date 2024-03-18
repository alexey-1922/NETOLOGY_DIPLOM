from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from backend.models import User, Shop

class TestAccountDetails(APITestCase):
    """
    Test for getting and modifying account detail
    """
    def setUp(self):
        # Create a user for testing
        
        self.user = User.objects.create_user(first_name='rirst_name', last_name = 'last_name', email = 'test.gmail.com', 
                                             password ='password', company = 'company', position = 'position')

    def test_get_account_details_authenticated(self):
        # Log in the user
        self.client.force_login(self.user)

        # Send a GET request to the view
        url = reverse('account_details')
        response = self.client.get(url)

        # Assert the response status code and content
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['first_name'], 'first_name')  # Adjust this based on your serializer

    def test_get_account_details_unauthenticated(self):
        # Send a GET request to the view without authenticating
        url = reverse('account_details')
        response = self.client.get(url)

        # Assert the response status code and content
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {'Status': False, 'Error': 'Требуется вход в систему'})

    def test_update_account_details_authenticated(self):
        # Log in the user
        self.client.force_login(self.user)

        # Send a POST request to update account details
        data = {'email': 'newemail@example.com'}  # Adjust data as needed
        url = reverse('account_details')
        response = self.client.post(url, data, format='json')

        # Assert the response status code and content
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'Status': True})

        # Refresh the user instance from the database
        self.user.refresh_from_db()

        # Assert that the user's details have been updated
        self.assertEqual(self.user.email, 'newemail@example.com')

    def test_update_account_details_unauthenticated(self):
        # Send a POST request to update account details without authenticating
        url = reverse('account_details')
        response = self.client.post(url, {'email': 'newemail@example.com'})

        # Assert the response status code and content
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {'Status': False, 'Error': 'Требуется вход в систему'})
        
    
    
    
    
class TestPartnerStateView(APITestCase):
    """
    Test for getting and modifying partner state
    """
    def setUp(self):
        # Create a user with type 'shop' for testing
        self.shop_user = User.objects.create_user(first_name='first_shop', last_name = 'last_shop', email = 'shop.gmail.com', 
                                             password ='password', company = 'company', position = 'position', type='shop')
        # Create a shop associated with the shop user
        self.shop = Shop.objects.create(user=self.shop_user, name='Test Shop', state=True)

    def test_get_partner_state_authenticated_shop_user(self):
        # Log in the shop user
        self.client.force_login(self.shop_user)

        # Send a GET request to the PartnerState view
        url = reverse('partner_state')  # Adjust the URL based on your project's URL configuration
        response = self.client.get(url)

        # Assert the response status code and content
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {'id': self.shop.id, 'name': 'Test Shop', 'user_id': self.shop.user_id, 'state': True})

    def test_get_partner_state_unauthenticated(self):
        # Send a GET request to the PartnerState view without authenticating
        url = reverse('partner_state')  # Adjust the URL based on your project's URL configuration
        response = self.client.get(url)

        # Assert the response status code and content
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.json(), {'Status': False, 'Error': 'Требуется вход в систему'})

    def test_get_partner_state_authenticated_second_shop_user(self):
        # Create a user with type other than 'shop'
        second_shop_user = User.objects.create_user(first_name='second_shop_user', last_name = 'second_shop', email = 'shop_second.gmail.com', 
                                             password ='password', company = 'company', position = 'position', type='customer')

        # Log in the non-shop user
        self.client.force_login(second_shop_user)

        # Send a GET request to the PartnerState view
        url = reverse('partner_state')  # Adjust the URL based on your project's URL configuration
        response = self.client.get(url)

        # Assert the response status code and content
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.json(), {'Status': False, 'Error': 'Только для магазинов'})

    def test_post_partner_state_authenticated_shop_user(self):
        # Log in the shop user
        self.client.force_login(self.shop_user)

        # Send a POST request to the PartnerState view
        url = reverse('partner_state')  # Adjust the URL based on your project's URL configuration
        data = {'state': 'false'}  # Adjust the data based on your view's requirements
        response = self.client.post(url, data, format='json')

        # Assert the response status code and content
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {'Status': True})
        # Add more assertions based on your view's behavior

    def test_post_partner_state_unauthenticated(self):
        # Send a POST request to the PartnerState view without authenticating
        url = reverse('partner_state')  # Adjust the URL based on your project's URL configuration
        data = {'state': 'false'}  # Adjust the data based on your view's requirements
        response = self.client.post(url, data, format='json')

        # Assert the response status code and content
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.json(), {'Status': False, 'Error': 'Требуется вход в систему'})

    def test_post_partner_state_authenticated_second_shop_user(self):
        # Create a user with type other than 'shop'
        second_shop_user = User.objects.create_user(first_name='second_shop_user', last_name = 'second_shop', email = 'shop_second.gmail.com', 
                                             password ='password', company = 'company', position = 'position', type='customer')

        # Log in the non-shop user
        self.client.force_login(second_shop_user)

        # Send a POST request to the PartnerState view
        url = reverse('partner_state')  # Adjust the URL based on your project's URL configuration
        data = {'state': 'false'}  # Adjust the data based on your view's requirements
        response = self.client.post(url, data, format='json')

        # Assert the response status code and content
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.json(), {'Status': False, 'Error': 'Только для магазинов'})