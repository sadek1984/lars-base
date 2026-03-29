# LARS - Laboratory Analytics & Risk System

> 🔒 **Security Notice**: This system implements **Schema-Only Prompting** for AI queries. No sensitive laboratory data (client names, test results, sample IDs) is sent to external APIs. Only metadata (column names, types, structure) is transmitted. See [Security Documentation](docs/SECURITY_SCHEMA_ONLY_PROMPTING.md) for details.

## Features
- 📊 **Pesticide Data Analysis** - AI-powered analytics for laboratory test results
- 🔬 **ISO 17025 Compliance** - Built for accredited laboratories
- 🤖 **Smart AI Assistant** - Natural language queries in Arabic and English
- 🔒 **Privacy-First Design** - Schema-only prompting ensures data never leaves your server
- 📈 **Predictive Analytics** - Trend analysis and risk assessment
- 🗺️ **Interactive Maps** - Geographic visualization of compliance data
- 🧬 **Dietary Exposure Assessment (NEW)** - PRIMo 4 methodology implementation:
  - ADI-based risk calculations (EDI, HQc, HIc)
  - 9 population classes with PRIMo 4 body weights
  - Chemical group classification (Pyrethroids, Organophosphates, Carbamates, etc.)
  - EU MRL API integration for current limits
  - Risk visualization by chemical group

This is a minimal implementation of the RAG model for Excel files retrieval.
## Requirements ›
- Python 3.8 or later
#### Install Python using MiniConda
1) Download and install MiniConda from [here] (https://docs. anaconda.com/free/miniconda/#quick-command-line-install)
2) Create a new environment using the following command:
```bash
$ conda create -n mini-rag python=3.8
```
3) Activate the environment:
```bash
$ conda activate mini-rag-app
```
## Installation
### Install the required packages
```bash
$ pip install -r requirements.txt , pip install -r src/requirements.txt
```
### Setup the environment variables
```bash
$ cp .env.example .env
```
Set your environment variables in the `.env` file. Like `OPENAI_API_KEY` value.
## Run Docker Compose Services

```bash
$ cd docker
$ cp .env.example. env
update '.env with your

## Run the FastAPI server
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8001

uvicorn src.main:app --reload --host 0.0.0.0 --port 8001
``` 
## POSTMAN Collection
origin  git@github.com:yourusername/repo.git(fetch)

## Difference between branches
git diff --name-only LARS_predict pre_final
git diff LARS_predict pre_final -- path/to/suspected_file.py
git diff LARS_predict..pre_final


 
Download the POSTMAN collection from [/assets/mini-rag-app.postman_collection.json](/ assets/mini-rag-app.postman_collection.json)
# fastapi boilerplate github --> use template from others

*** for devlopmenet only not used in production {
# Show all containers
docker ps -a
# If there are containers, remove them
docker rm $(docker ps -aq)
ولو عايز تحذف حتى الـ running containers كمان، لازم توقفهم الأول:
docker stop $(docker ps -aq)
docker rm $(docker ps -aq)}

# push to github
git push -u origin <your-branch-name>
git push -u origin Dashboard
# ollama serve from cli
/usr/local/bin/ollama serve
# run serve in colab background
!nohup ollama serve & 
!sleep 5 && tail /content/nohup.out
# to run colab server on local machine
ngrok

# Make pg_config available
brew install libpq
brew link --force libpq

# to create database
alembic revision --autogenerate -m "Initial Commit" # from minirag folder
# Apply the migration to the database
alembic upgrade head

# gemini-1.5-flash-latest API
"AIzaSyAND7ureFwWN614Fd6APcNyaBVOm3zkN3c"

# to browse data from docker
docker compose exec fastapi ls -la /app/data/2024/Feb/
# ______________________________________________________

##### instal claude agent 
specify init . --ai claude --ignore-agent-tools

docker compose down 

docker compose up --build


streamlit run src/LARS/app_new.py






find bifenazate in tomato

find bifenthrin in all samples 

Find 'Buprofezin' more than 2 times the limit in tomato samples

find non compliant samples with bifenthrin in cucumber samples 
what tomato samples is non compliant with bifenthrin?
                        ـــــــــــــــــــــــــــــــــــــــ        

 ما عدد عينات الطماطم و الخيار و الكوسة كل علي حده

ما هو عدد العينات التي تحتوي علي عدد ٦ مبيد

ما هو عدد العينات التي تحتوي علي عدد مبيد واحد و عدد ٢ مبيد كل علي حده

ابحث عن الفيبرونيل داخل الفاصوليا
ابحث عن imidacloprid في الفستق

ما عدد عينات الطماطم التي تكون فيها القراءة اكبر من الحدود

ما هي الخضروات التي يشملها مبيد البايفنثرن

ما هي عينات الكوسه و الباذنجان التي تحتوي علي مبيد bifenthrin 

ما هي انواع التوابل الموجودة في حي الاسكان 

ما هي عينات الطماطم التي تحتوي علي مبيد البابروفيزن  

عينات تحتوي على الكلوربيريفوس فوق الحد

ما هي عينات الطماطم التي تحتوي علي مبيد البابروفيزن الغير مطابقة

ماهي المبيدات الموجوده في عينة الطماطم  و ما عدد تكرار المبيدات

                        ـــــــــــــــــــــــــــــــــــــــ        

ماهي المبيدات الموجوده في حي الريان و الإسكان كل علي حده

كم عدد عينات الخيار الفريدة بناءً على كود العينة؟
٢
ابحث عن العينات في منشأة محامص مذاق ضيافة الخير

ماهي عينات مشعل الرشيدي المطابقة الفريدة

ماهي عينات المكسرات للمستلم  أحمد الفايز

ماهي العينات الفريدة  الغير مطابقة  للمستلم  أحمد الفايز
######
اعرض الاحياء في ترتيب تنازلي من الاكثر الي الاقل مخالفه

اعطني المبيدات و السموم الفطريه  فوق الحد المسموح و تحت الحد المسموح للتوابل

كم عدد العينات التي تحتوي علي مبيد الايثيون

ماهو اعلي تركيز و اقل تركيز لمبيد الايميداكلوبرايد

ماهو المدي لتركيزات الايميداكلوبرايد في الطماطم

ماهو المتوسط و الوسيط لمبيد  الايميداكلوبرايد في الطماطم

Show me violations by neighborhood

   ما هو مؤشر الخطر الصحي لعينات الخيار بناءً على متوسط استهلاك الفرد في السعودية؟
  
  احسب مؤشر الجودة لعينات الفلفل

  ماهي العينات التي تحتوي علي 10 مبيدات و صنف هذه المبيدات

  what are the samples contain 10 pesticides?

أعطني ملخص المجموعات الكيميائية لكل عينة تحتوي على أكثر من ٣ مبيدات


ماهي المبيدات التي ظهرت في الهيل
مع التكرار و عدد المخالفات

 

 ما عينات الفلفل الراسبة

 ماعدد العينات الفريدة المخالفة في الهيل و ما عدد تكرار المبيدات

 كم عدد المبيدات التي ظهرت في كل عينات الطماطم وكم عدد المبيدات المتسببة في الرسوب


 كم تكرارية الايميداكلوبرايد في الطماطم

 ما متوسط تركيز الايميداكلوبريد في العينات فوق الحدود


اوجد عدد العينات الخالية من المبيدات والتي تحتوي على 1 مبيد والتي تحتوي على 3 مبيدات كل على حده