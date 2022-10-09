from distutils.log import error
from pydoc import render_doc
from django.shortcuts import render
from django.http import HttpResponse
import asyncio
import aiohttp
from dotenv import load_dotenv
import os

load_dotenv()
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
set_api_key = os.getenv('OPENAI_API_KEY')
responses = HttpResponse()

#Get prompts for GPT-3
def get_prompts(searchQuery):
    p1 = f"Explain in informative terms to a non programmer in 300 words. {searchQuery}"
    p2 = f"Give a roadmap that is a series of instructions that someone should take to solve this question. {searchQuery}"
    prompts = []
    explanation = {
        'prompt': p1,
        'temperature': 0.7,
        'max_tokens': 500,
        'top_p': 1,
        'frequency_penalty': 0,
        'presence_penalty': 0
    }
    roadmap = {
        'prompt': p2,
        'temperature': 0.7,
        'max_tokens': 500,
        'top_p': 1,
        'frequency_penalty': 0,
        'presence_penalty': 0
    }
    prompts.append(explanation)
    prompts.append(roadmap)
    return prompts

#Asynchronous functions to call OpenAI API and get text from GPT-3
async def get_text(session, url, params):
    async with session.post(url, json=params) as resp:
        text = await resp.json()
        return text['choices'][0]['text']

async def results_async(searchQuery):
    prompts = get_prompts(searchQuery)
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False), headers={'authorization': f"Bearer {set_api_key}"}) as session:
        tasks = []
        for prompt in prompts:
            url = 'https://api.openai.com/v1/engines/text-davinci-002/completions'
            tasks.append(asyncio.ensure_future(get_text(session, url, prompt)))
        feedbacks = await asyncio.gather(*tasks)
    return {'response': feedbacks[0], 'query': searchQuery, 'roadmap': feedbacks[1]}

#Results page
def results(response):
    error = responses.get('error')
    print(error)
    if error == "True":    
        return render(response, 'error.html')
    else:
        search_query = responses.get('query')
        numResults = 2
        resps = asyncio.run(results_async(search_query))
        return render(response, 'result.html', resps)

#About us page
def about(response):
    return render(response, 'aboutUs.html')

#Search page
def search(response):
    return render(response, 'index.html')

#Query view to get query from search page (PLEASE ADVISE IF BETTER WAY)
def query(request):
    if request.method == 'POST':
        if 'query' in request.POST:
            q = str(request.POST['query'])
            error = False
            if "?" in q:
                responses.headers['query'] = q
            else:
                error = True
            responses.headers['error'] = error
