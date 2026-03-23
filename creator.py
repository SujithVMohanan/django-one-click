import sys
import subprocess
from pathlib import Path
import shutil




# Environment content
env_content = """SECRET_KEY=""
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost
DATABASE_NAME=""
DATABASE_USER=""
DATABASE_PASSWORD=""
DATABASE_HOST="localhost"
DATABASE_PORT="5432"
DEFAULT_API_URL='http://127.0.0.1/'
"""



models_content = """
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import (
    AbstractBaseUser,
    PermissionsMixin,
    BaseUserManager
)


class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UserManager(BaseUserManager):

    def create_user(self, username, password=None, **extra_fields):
        if not username:
            raise ValueError("Username is required")

        user = self.model(
            username=username,
            **extra_fields
        )

        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra_fields):

        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_admin', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError("Superuser must have is_staff=True")

        if extra_fields.get('is_superuser') is not True:
            raise ValueError("Superuser must have is_superuser=True")

        return self.create_user(username, password, **extra_fields)


def user_directory_path(instance, filename):
    return f'users/{instance.username}/{filename}'


class Users(AbstractBaseUser, PermissionsMixin, BaseModel):

    username = models.CharField(_('username'), max_length=100, unique=True)
    name = models.CharField(max_length=100, blank=True, null=True)
    password = models.CharField(_('password'), max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(_('email'), max_length=255, blank=True, null=True)
    image = models.FileField(upload_to=user_directory_path, blank=True, null=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    is_admin = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['name', 'phone', 'email']

    class Meta:
        ordering = ['id']
        verbose_name = _('user')
        verbose_name_plural = _('users')

    def __str__(self):
        return f"{self.username}"
"""


users_schemas = """
from rest_framework import serializers
from apps.users.models import Users


class GetUsersSchema(serializers.ModelSerializer):

    class Meta:
        model = Users
        fields = [
            'id', 'username', 'phone', 'email', 'image',
            'is_active', 'is_staff', 'is_superuser', 'is_admin'
        ]

    def to_representation(self, instance):
        datas = super().to_representation(instance)
        for key in datas.keys():
            try:
                if datas[key] is None:
                    datas[key] = ""
            except KeyError:
                pass
        return datas


class LoginResponseSchema(serializers.ModelSerializer):

    class Meta:
        model = Users
        fields = ['id', 'username', 'email', 'phone', 'image']

    def to_representation(self, instance):
        datas = super().to_representation(instance)
        for key in datas.keys():
            try:
                if datas[key] is None:
                    datas[key] = ""
            except KeyError:
                pass
        return datas
"""



user_serializers = """
from rest_framework import serializers

from apps.users.models import Users
from helpers.helpers import (
    base64_to_image,
)




class LoginSerializer(serializers.ModelSerializer):
    username = serializers.CharField()
    password = serializers.CharField()
    
    class Meta:
        model = Users
        fields = ['username','password']
        
    def validate(self, attrs):
        return super().validate(attrs)    



class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()
    


class RegisterUserSerializer(serializers.ModelSerializer):
    username            = serializers.CharField(required=True)
    email               = serializers.EmailField(required=True)
    password            = serializers.CharField(required=True)
    confirm_password    = serializers.CharField(required=True,write_only=True)
    image               = serializers.CharField(required=False, allow_null=True)

    class Meta:
        model = Users
        fields = ['username', 'email', 'password','confirm_password','image']

    def validate(self, attrs):
        if Users.objects.filter(username=attrs.get('username')).exists():
            raise serializers.ValidationError("Username already exists.")
        
        if Users.objects.filter(email=attrs.get('email')).exists():
            raise serializers.ValidationError("Email already exists.")
        
        if attrs.get('password') != attrs.get('confirm_password'):
            raise serializers.ValidationError("Password and Confirm Password do not match.")
        
        return super().validate(attrs)

    def create(self, validated_data):

        validated_data.pop('confirm_password',None)
        password       = validated_data.pop('password',None)
        user           = Users()
        user.username  = validated_data.get('username','')
        user.email     = validated_data.get('email','') 


        base64_image = validated_data.pop('image',None)
        if base64_image:
            image_file   = base64_to_image(base64_image)
            user.image = image_file

        if password:
            user.set_password(password)

        user.save()

        return user

"""



views_content="""
import os,sys
from rest_framework import generics, permissions, filters, status
from rest_framework_simplejwt.tokens import RefreshToken
from apps.users.models import Users
from helpers.response import ResponseInfo
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django_filters.rest_framework import DjangoFilterBackend
from helpers.pagination import RestPagination

from django.contrib import auth
from rest_framework.response import Response
from helpers.helpers import (
    get_object_or_none,
)

from apps.users.schemas import (
    GetUsersSchema,
    LoginResponseSchema
)

from apps.users.serializers import (
    LoginSerializer,
    LogoutSerializer,
    RegisterUserSerializer,
)


class LoginAPIView(generics.GenericAPIView):
    def __init__(self, **kwargs):
        self.response_format = ResponseInfo().response
        super(LoginAPIView, self).__init__(**kwargs)

    serializer_class = LoginSerializer

    @swagger_auto_schema(tags=["Authorization"])
    def post(self, request):
        try:

            serializer = self.serializer_class(data=request.data)
            
            if not serializer.is_valid():
                self.response_format['status_code'] = status.HTTP_400_BAD_REQUEST
                self.response_format["status"] = False
                self.response_format["errors"] = serializer.errors
                return Response(self.response_format, status=status.HTTP_400_BAD_REQUEST)
            
            user = auth.authenticate(username=serializer.validated_data.get('username',''), password=serializer.validated_data.get('password',''))

            if not user:
                self.response_format['status_code'] = status.HTTP_400_BAD_REQUEST
                self.response_format["message"] = "Invalid username or password"
                self.response_format["status"] = False
                return Response(self.response_format, status=status.HTTP_200_OK)

            if user:
                
                serializer = LoginResponseSchema(user, context={"request": request})

                if not user.is_active:
                    data = {'user': {}, 'token': '', 'refresh': ''}
                    self.response_format['status_code'] = status.HTTP_202_ACCEPTED
                    self.response_format["data"] = data
                    self.response_format["status"] = False
                    self.response_format["message"] = "Account is suspended"
                    return Response(self.response_format, status=status.HTTP_200_OK)
                
            
            refresh = RefreshToken.for_user(user)
            
            token = str(refresh.access_token)
            data = {'user': serializer.data, 'token':token, 'refresh': str(refresh)}
            self.response_format['status_code'] = status.HTTP_200_OK
            self.response_format["data"] = data
            self.response_format["status"] = True
            return Response(self.response_format, status=status.HTTP_200_OK)
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
       
            
            self.response_format['status_code'] = status.HTTP_500_INTERNAL_SERVER_ERROR
            self.response_format['status'] = False
            self.response_format['message'] = str(e)
            return Response(self.response_format, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class LogoutAPIView(generics.GenericAPIView):
    def __init__(self, **kwargs):
        self.response_format = ResponseInfo().response
        super(LogoutAPIView, self).__init__(**kwargs)

    serializer_class = LogoutSerializer

    @swagger_auto_schema(tags=["Authorization"])
    def post(self, request):
        try:

            refresh_token = request.data.get("refresh")

            if not refresh_token:
                return Response(
                    {"message": "Refresh token required"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            token = RefreshToken(refresh_token)
            token.blacklist()

            self.response_format['status_code'] = status.HTTP_200_OK
            self.response_format["message"] = "Logout successful"
            self.response_format["status"] = True
            return Response(self.response_format, status=status.HTTP_200_OK)
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            self.response_format['status_code'] = status.HTTP_500_INTERNAL_SERVER_ERROR
            self.response_format['status'] = False
            self.response_format['message'] = str(e)
            return Response(self.response_format, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GetUsersApiView(generics.GenericAPIView):
    
    def __init__(self, **kwargs):
        self.response_format = ResponseInfo().response
        super(GetUsersApiView, self).__init__(**kwargs)

    
    serializer_class    = GetUsersSchema
    permission_classes  = [permissions.IsAuthenticated]
    queryset            = Users.objects.all().order_by('id')
    pagination_class    = RestPagination


    filter_backends     = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields       = ['id']

    @swagger_auto_schema(tags=["Users"],
        manual_parameters=[
            openapi.Parameter(
                name='id',
                in_=openapi.IN_QUERY,
                description='Search by employee ID',
                type=openapi.TYPE_STRING
            ),
        ]

    )
    def get(self, request, *args, **kwargs):
        emp_id = request.GET.get('id', None)
        if emp_id is not None:
            employess = self.queryset.filter(id=emp_id)
        else:
            employess = self.queryset.all().order_by('id')

        page = self.paginate_queryset(employess)
        serializer = self.serializer_class(page, many=True, context={'request': request})
        return self.get_paginated_response(serializer.data)



class RegisterUserApiView(generics.GenericAPIView):
    def __init__(self, **kwargs):
        self.response_format = ResponseInfo().response
        super(RegisterUserApiView, self).__init__(**kwargs)

    serializer_class = RegisterUserSerializer
    response_schema  = GetUsersSchema

    @swagger_auto_schema(tags=["Users"])
    def post(self, request):
        try:

            serializer = self.serializer_class(data=request.data)
            if not serializer.is_valid():
                self.response_format['status_code'] = status.HTTP_400_BAD_REQUEST
                self.response_format["status"] = False
                self.response_format["errors"] = serializer.errors
                return Response(self.response_format, status=status.HTTP_400_BAD_REQUEST)
            
            serializer.save()
            self.response_format['status_code'] = status.HTTP_200_OK
            self.response_format["data"] = serializer.data
            self.response_format["status"] = True
            return Response(self.response_format, status=status.HTTP_200_OK)
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
       
            
            self.response_format['status_code'] = status.HTTP_500_INTERNAL_SERVER_ERROR
            self.response_format['status'] = False
            self.response_format['message'] = str(e)
            return Response(self.response_format, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
"""


user_urls_content="""

from django.urls import path


from apps.users.views import (
    GetUsersApiView,
    LoginAPIView,
    LogoutAPIView,
    RegisterUserApiView,
)


urlpatterns = [
    path('login/', LoginAPIView().as_view(), name='login'),
    path('logout/', LogoutAPIView().as_view(), name='logout'),
    path('register/', RegisterUserApiView().as_view(), name='register'),
    path('list-users/', GetUsersApiView().as_view(), name='list_users'),
]

"""


helpers_content = {
    
    "pagination.py": """
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework import status
from helpers.response import ResponseInfo

class RestPagination(PageNumberPagination):
    
    page_size = 10
    page_size_query_param = 'limit'
    
    def __init__(self, **kwargs):
        self.response_format = ResponseInfo().response
        super(RestPagination, self).__init__(**kwargs)

    def get_paginated_response(self, data):
        data = {
            'links': {
                'next': "" if self.get_next_link() is None else self.get_next_link().split('/api')[1],
                'previous': "" if self.get_previous_link() is None else self.get_previous_link().split('/api')[1]
            },
            'count': self.page.paginator.count,
            'results': data,
            'heading':{}
        }
        
        self.response_format['status_code'] = status.HTTP_200_OK
        self.response_format["data"] = data
        self.response_format["status"] = True
        
        return Response(self.response_format, status=status.HTTP_200_OK)


class CustomRestPagination(PageNumberPagination):
    
    page_size = 10
    page_size_query_param = 'limit'
    
    def __init__(self, **kwargs):
        super(CustomRestPagination, self).__init__(**kwargs)

    def get_paginated_response(self, data):
        data = {
            'links': {
                'next': "" if self.get_next_link() is None else self.get_next_link().split('/api')[1],
                'previous': "" if self.get_previous_link() is None else self.get_previous_link().split('/api')[1]
            },
            'count': self.page.paginator.count,
            'results': data,
            'heading':{}
        }
        return data
""",

    "helpers.py": """
import base64
import uuid
from django.core.files.base import ContentFile

def base64_to_image(base64_string):
    if ';base64,' in base64_string:
        format, imgstr = base64_string.split(';base64,')
        ext = format.split('/')[-1]
    else:
        imgstr = base64_string
        ext = "png"
    file_name = f"{uuid.uuid4()}.{ext}"
    return ContentFile(base64.b64decode(imgstr), name=file_name)

def get_object_or_none(classmodel, **kwargs):
    try:
        return classmodel.objects.get(**kwargs)
    except classmodel.DoesNotExist:
        return None
""",

    "error_messages.py": """
def get_error_message(error):
    if hasattr(error, "messages"):
        return " ".join(error.messages)
    return str(error)
""",

    "response.py": """
class ResponseInfo(object):
    def __init__(self, user=None, **args):
        self.response = {
            "status"        : args.get('status', True),
            "status_code"   : args.get('status_code', 200),
            "message"       : args.get('message', ''),
            "data"          : args.get('data', {}),
            "errors"        : args.get('errors', {}),
        }
""",

    "exceptions.py": """
from rest_framework.views import exception_handler

def get_response(message="", result={}, status=False, status_code=200):
    return {
        "status": status,
        "status_code": status_code,
        "message": message,
        "data": result,
    }

def get_error_message(error_dict):
    field = next(iter(error_dict))
    response = error_dict[next(iter(error_dict))]
    if isinstance(response, dict):
        response = get_error_message(response)
    elif isinstance(response, list):
        response_message = response[0]
        if isinstance(response_message, dict):
            response = get_error_message(response_message)
        else:
            response = response[0]
    return response

def handle_exception(exc, context):
    error_response = exception_handler(exc, context)
    if error_response is not None:
        error = error_response.data

        if isinstance(error, list) and error:
            if isinstance(error[0], dict):
                error_response.data = get_response(
                    message=get_error_message(error),
                    status_code=error_response.status_code,
                )
            elif isinstance(error[0], str):
                error_response.data = get_response(
                    message=error[0],
                    status_code=error_response.status_code
                )

        if isinstance(error, dict):
            error_response.data = get_response(
                message=get_error_message(error),
                status_code=error_response.status_code
            )
    return error_response
"""
}



urls_content="""
\"\"\"
URL configuration for chatbot project.
\"\"\"

from django.contrib import admin
from django.urls import path, include, re_path
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from django.conf import settings
from django.conf.urls.static import static

schema_view = get_schema_view(
    openapi.Info(
        title="ChatBot API",
        default_version='v1',
        description="Advanced API with JWT, pagination, filters, and Swagger",
        contact=openapi.Contact(email="sujith.avrs@gmail.com"),
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
)

urlpatterns = [
    path('admin/', admin.site.urls),

    re_path(r'^api/', include([
    
        path('users/', include('apps.users.urls')),

        re_path(r'^docs/', include([
            path('', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
            path('redoc', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
        ])),
    ])),
]

# Serve static/media files in development
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
"""

class DjangoFullProjectSetup:
    def __init__(self, folder_path: str, project_name: str):
        self.folder_path = Path(folder_path)
        self.project_name = project_name
        self.packages = [
            "Django",
            "python-dotenv",
            "djangorestframework",
            "drf-yasg",
            "djangorestframework_simplejwt",
            "django-filter",
            "psycopg2-binary"
        ]

        self.venv_python = None
        self.activate_script = None

        # Paths
        self.apps_folder = self.folder_path / "apps"
        self.helpers_folder = self.folder_path / "helpers"
        self.project_folder = self.folder_path / project_name

    # ----------------------------
    # Step 1: Create Project Folder
    # ----------------------------
    def create_folder(self):
        self.folder_path.mkdir(parents=True, exist_ok=True)
        print(f"✅ Project folder ready: {self.folder_path}")

    # ----------------------------
    # Step 2: Create Virtual Environment
    # ----------------------------
    def create_venv(self):
        print("🔹 Creating virtual environment...")
        subprocess.run(["python", "-m", "venv", "venv"], cwd=self.folder_path, check=True)
        if sys.platform == "win32":
            self.venv_python = self.folder_path / "venv" / "Scripts" / "python.exe"
            self.activate_script = "venv\\Scripts\\activate"
        else:
            self.venv_python = self.folder_path / "venv" / "bin" / "python"
            self.activate_script = "source venv/bin/activate"

    # ----------------------------
    # Step 3: Upgrade pip
    # ----------------------------
    def upgrade_pip(self):
        print("🔹 Upgrading pip...")
        subprocess.run([str(self.venv_python), "-m", "pip", "install", "--upgrade", "pip"], check=True)

    # ----------------------------
    # Step 4: Install packages
    # ----------------------------
    def install_packages(self):
        print("🔹 Installing packages...")
        subprocess.run([str(self.venv_python), "-m", "pip", "install", *self.packages], check=True)
        print("✅ Packages installed")

    # ----------------------------
    # Step 5: Create Django Project
    # ----------------------------
    def create_project(self):
        print("🔹 Creating Django project...")
        subprocess.run([str(self.venv_python), "-m", "django", "startproject", self.project_name, "."],
                       cwd=self.folder_path, check=True)
        print(f"✅ Django project '{self.project_name}' created")

    # ----------------------------
    # Step 6: Create extra folders
    # ----------------------------
    def create_extra_folders(self):
        print("🔹 Creating extra project folders...")
        for folder in ["apps", "media", "templates", "helpers", "static"]:
            path = self.folder_path / folder
            path.mkdir(exist_ok=True)
            print(f"   ✔ {folder}/ created")

    # ----------------------------
    # Step 7: Generate requirements.txt
    # ----------------------------
    def generate_requirements(self):
        print("🔹 Generating requirements.txt...")
        req_file = self.folder_path / "requirements.txt"
        with open(req_file, "w") as f:
            for pkg in self.packages:
                pkg_name = pkg.split("==")[0]
                result = subprocess.run([str(self.venv_python), "-m", "pip", "show", pkg_name],
                                        capture_output=True, text=True, check=True)
                for line in result.stdout.splitlines():
                    if line.startswith("Version:"):
                        version = line.split(":", 1)[1].strip()
                        f.write(f"{pkg_name}=={version}\n")
                        break
        print("✅ requirements.txt created")

    # ----------------------------
    # Step 8: Create .env
    # ----------------------------
    def create_env(self):
        print("🔹 Creating .env file...")
        env_file = self.folder_path / ".env"
        env_file.write_text(env_content, encoding="utf-8")
        print(f"✅ .env file created at {env_file}")

    # ----------------------------
    # Step 9: Update settings.py
    # ----------------------------
    def update_settings(self):
        print("🔹 Creating settings.py...")
        settings_path = self.project_folder / "settings_new.py"

        
        settings_content=f'''
"""
Django settings for chatbot project.
"""

from pathlib import Path
from dotenv import load_dotenv, find_dotenv
import os, datetime

load_dotenv(find_dotenv(), override=True, verbose=True)

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY','')

DEBUG = True if os.environ.get("DEBUG","True").lower() == "true" else False

ALLOWED_HOSTS = os.environ.get(
    "ALLOWED_HOSTS",
    "127.0.0.1,localhost"
).split(",")

# --------------------------------
# Apps
# --------------------------------
LOCAL_APPS=[
    'apps.users',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'drf_yasg',
    'django_filters',
    'rest_framework_simplejwt.token_blacklist',
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
] + LOCAL_APPS + THIRD_PARTY_APPS

# --------------------------------
# Middleware
# --------------------------------
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = '{self.project_name}.urls'

TEMPLATES = [
    {{
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / "templates"],
        'APP_DIRS': True,
        'OPTIONS': {{
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        }},
    }},
]

WSGI_APPLICATION = '{self.project_name}.wsgi.application'

# --------------------------------
# Database
# --------------------------------
DATABASES = {{
    "default": {{
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DATABASE_NAME"),
        "USER": os.environ.get("DATABASE_USER"),
        "PASSWORD": os.environ.get("DATABASE_PASSWORD"),
        "HOST": os.environ.get("DATABASE_HOST", "localhost"),
        "PORT": os.environ.get("DATABASE_PORT", "5432"),
    }}
}}

# --------------------------------
# Auth
# --------------------------------
AUTH_USER_MODEL = 'users.Users'

# --------------------------------
# Static & Media
# --------------------------------
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / "media"

# --------------------------------
# Swagger
# --------------------------------
SWAGGER_SETTINGS = {{
    'DEFAULT_API_URL': os.environ.get("DEFAULT_API_URL"),
    'USE_SESSION_AUTH': False,
    'SECURITY_DEFINITIONS': {{
        'Basic': {{'type': 'basic'}},
        'Bearer': {{
            'type': 'apiKey',
            'name': 'Authorization',
            'in': 'header'
        }}
    }},
}}

# --------------------------------
# DRF
# --------------------------------
REST_FRAMEWORK = {{
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10,
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ),
    'EXCEPTION_HANDLER': 'helpers.exceptions.handle_exception'
}}

# --------------------------------
# JWT
# --------------------------------
SIMPLE_JWT = {{
    'ACCESS_TOKEN_LIFETIME': datetime.timedelta(days=20),
    'REFRESH_TOKEN_LIFETIME': datetime.timedelta(days=50),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': False,
    'UPDATE_LAST_LOGIN': True,

    'ALGORITHM': 'HS256',
    'SIGNING_KEY': 'ssseShVmYq3t6w9z$C&E)H@McQfTjWnZr4u7x!A%D*G-JaNdRgUkXp2s5v8y/B?E(H+',
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': None,

    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'USER_AUTHENTICATION_RULE': 'rest_framework_simplejwt.authentication.default_user_authentication_rule',
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',

    'JTI_CLAIM': 'jti',

    'SLIDING_TOKEN_REFRESH_EXP_CLAIM': 'refresh_exp',
    'SLIDING_TOKEN_LIFETIME': datetime.timedelta(days=20),
    'SLIDING_TOKEN_REFRESH_LIFETIME': datetime.timedelta(days=50),
}}
'''

        settings_path.write_text(settings_content.strip(), encoding="utf-8")
        print(f"✅ settings.py created at {settings_path}")


    # ----------------------------
    # Step 9: Update urls.py
    # ----------------------------
    def update_main_urls(self):
        print("🔹 Creating settings.py...")
        urls_path = self.project_folder / "urls.py"
        urls_path.write_text(urls_content.strip(), encoding="utf-8")
        print(f"✅ settings.py created at {urls_path}")


    # ----------------------------
    # Step 10: Create Users App
    # ----------------------------
    def create_users_app(self):
        print("🔹 Creating users app...")
        manage_py = self.folder_path / "manage.py"

        # Path where startapp will create the app
        users_app_path = self.folder_path / "users"

        # Only create app if it doesn't already exist
        if not users_app_path.exists():
            subprocess.run(
                [str(self.venv_python), str(manage_py), "startapp", "users"],
                cwd=self.folder_path,
                check=True
            )
            print("✅ Django app 'users' created")
        else:
            print("⚠ 'users' app already exists, skipping startapp")

        # Move users app to apps/ folder
        dst = self.apps_folder / "users"
        self.apps_folder.mkdir(exist_ok=True)
        if users_app_path.exists() and not dst.exists():
            shutil.move(str(users_app_path), str(dst))
            print("✅ users app moved to apps/users")
        elif dst.exists():
            print("⚠ users app already in apps/users, skipping move")

    # ----------------------------
    # Step 11: Populate Users App with all files
    # ----------------------------
    def populate_users_app(self):
        print("🔹 Populating users app files...")
        users_app = self.apps_folder / "users"
        # Create folders
        folders = [
            users_app / "services",
            users_app / "management",
            users_app / "management" / "commands",
        ]
        for folder in folders:
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "__init__.py").touch(exist_ok=True)

        # Files content
        files_content = {
            "models.py": models_content,
            "serializers.py": user_serializers,
            "views.py": views_content,
            "schemas.py": users_schemas,
            "urls.py": user_urls_content,
            "apps.py": """from django.apps import AppConfig

class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.users'
""",
        }

        for fname, content in files_content.items():
            (users_app / fname).write_text(content.strip(), encoding="utf-8")
            print(f"   ✔ {fname} created")

        # Init migrations command
        cmd_path = users_app / "management" / "commands" / "init_migrations.py"
        cmd_path.write_text("""
from django.core.management.base import BaseCommand
from django.core.management import call_command

class Command(BaseCommand):
    help = "Run makemigrations and migrate together"

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING("Running makemigrations..."))
        call_command('makemigrations')
        self.stdout.write(self.style.WARNING("Running migrate..."))
        call_command('migrate')
        self.stdout.write(self.style.SUCCESS("Database synced successfully ✅"))
""", encoding="utf-8")
        
        print("✅ init_migrations command created")

    # ----------------------------
    # Step 12: Create helpers
    # ----------------------------
    def create_helpers(self):
        print("🔹 Creating helpers folder & files...")
        self.helpers_folder.mkdir(exist_ok=True)
        for fname, content in helpers_content.items():
            (self.helpers_folder / fname).write_text(content.strip(), encoding="utf-8")
        print("✅ helpers created")

    # ---------------------------
    # Step 13: Run init_migrations
    # ---------------------------
    def run_migrations(self):
        """Runs 'python manage.py init_migrations'."""
        print("🔹 Running makemigrations + migrate...")

        manage_py = self.folder_path / "manage.py"
        subprocess.run(
            [str(self.venv_python), str(manage_py), "init_migrations"],
            cwd=self.project_folder,
            check=True
        )
        print("✅ Database migrations complete")

        
    # ----------------------------
    # Step 14: Open CMD
    # ----------------------------
    def open_cmd(self):
        print("🔹 Opening CMD...")
        activate_cmd = f'cd /d "{self.folder_path}" && {self.activate_script}'
        subprocess.run(f'start cmd /K "{activate_cmd}"', shell=True)

    # ----------------------------
    # Run all steps
    # ----------------------------
    def run(self):
        self.create_folder()
        self.create_venv()
        self.upgrade_pip()
        self.install_packages()
        self.create_project()
        self.create_extra_folders()
        self.generate_requirements()
        self.create_env()
        self.update_settings()
        self.update_main_urls()
        self.create_users_app()
        self.populate_users_app()
        self.create_helpers()
        # self.run_migrations()
        # self.open_cmd()
        print("\n🎉 Full Django project setup completed!")


if __name__ == "__main__":
    setup = DjangoFullProjectSetup(folder_path="D:/aa/chat_bot", project_name="sujith_project")
    setup.run()