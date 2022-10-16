from __future__ import absolute_import
from __future__ import division, print_function, unicode_literals
from sumy.parsers.html import HtmlParser
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer as Summarizer
from sumy.nlp.stemmers import Stemmer
from sumy.utils import get_stop_words
from bs4 import BeautifulSoup
from distutils.log import error
from pydoc import render_doc
from django.shortcuts import render
from django.http import HttpResponse
import asyncio
import aiohttp
from dotenv import load_dotenv
import os
from search_engine_parser.core.engines.google import Search as GoogleSearch
from search_engine_parser.core.engines.yahoo import Search as YahooSearch
import nest_asyncio
from nltk.stem import WordNetLemmatizer
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from urllib.request import urlopen


load_dotenv()
#asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
nest_asyncio.apply()
set_api_key = os.getenv('OPENAI_API_KEY')
responses = HttpResponse()
LANGUAGE = "english"
SENTENCES_COUNT = 10
lemmatizer = WordNetLemmatizer()


#Get prompts for GPT-3
def get_prompts(searchQuery):
    p1 = f"Explain in informative terms to a non programmer in 300 words. {searchQuery}"
    p2 = f"Give a roadmap that is a series of 5 steps that someone should take to solve this question. {searchQuery} The steps should be numbered as such: 1. First step, 2. Second step, 3. Third step, etc."
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

async def get_links(search_query):

    # returns a task that gets a list of tasks that grab links
    link_tasks = asyncio.run(get_link_handler(search_query, 1))

    # creating a list of tasks that grab the text from the links
    summaries_tasks = []

    # creating a list of links
    links = []

    # for each task that grabbed a list of links
    for task in link_tasks:
        # get the results of that task, which is a list of links
        result = task.result()

        # extend our list of links with the links from that task
        links.extend(result)

        # look through each link and create a task that generates a summary
        for link in result:
            summaries_tasks.append(asyncio.create_task(get_text_summary(link)))

    # wait for all the summaries to be generated
    await asyncio.gather(*summaries_tasks)

    # put each summary into a string with a number, to prompt gpt-3
    summaries_prompt = ""
    summaries = []


    # for i in range(len(summaries_tasks)):
    i = 0
    while i < len(summaries_tasks):
        result = summaries_tasks[i].result()
        if result.strip() != "":
            summaries.append(result)
            summaries_prompt += str(i + 1) + ") \"" + result[:800] + "\"\n"
            i += 1
        else:
            links.remove(links[i])
            summaries_tasks.remove(summaries_tasks[i])

    # prompt gpt-3 to choose the best 3 summaries
    summaries_prompt += "Which 3 of these texts best answer the prompt " + search_query + "? Answer with only numerical digits. Example Response: \"1,7,9\" or \"2,3,4\""

    prompt = {
        'prompt': summaries_prompt,
        'temperature': 0.7,
        'max_tokens': 256,
        'top_p': 1,
        'frequency_penalty': 0,
        'presence_penalty': 0
    }

    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False), headers={'authorization': f"Bearer {set_api_key}"}) as session:
        url = 'https://api.openai.com/v1/engines/text-davinci-002/completions'
        task = asyncio.ensure_future(get_text(session, url, prompt))
        nums = await task

    # get the response from gpt-3

    numbers = nums.strip().split(",")

    # filtering out text just in case GPT-3 returns something engineweird
    for num in numbers:
        num = "".join(filter(str.isdigit, num))

    # create a list of the links and summaries that gpt-3 chose
    final_links = [links[int(numbers[0])- 1], links[int(numbers[1]) - 1], links[int(numbers[2]) - 1]]
    final_summaries = [summaries[int(numbers[0]) - 1], summaries[int(numbers[1]) - 1], summaries[int(numbers[2]) - 1]]


    return {'link1': final_links[0], 'link2': final_links[1], 'summary1': final_summaries[0], 'summary2': final_summaries[1]}

async def get_link_handler(prompt, num_pages=1):
    tasks = []
    for i in range(1, num_pages + 1):
        tasks.append(asyncio.create_task(__get_links(prompt, i)))
    await asyncio.gather(*tasks)

    return tasks

async def __get_links(prompt, page_num):
    retry = 0
    results = None
    while retry < 3:
        try:
            results = GoogleSearch().search(prompt, page=page_num)
            break;
        except Exception as e:
            retry += 1
            if retry == 2:
                prompt = prompt[:-1]
    if results is None:
        retry = 0
        while retry < 3:
            try:
                results = YahooSearch().search(prompt, page=page_num)
                break;
            except Exception as e:
                retry += 1
    if results is None:
        return ""


    final_links = []

    results_links = results['links']
    for link in results_links:
        if link not in final_links and 'youtube' not in link:
            final_links.append(link)
    return final_links

async def get_text_summary(url):
    try:
        parser = HtmlParser.from_url(url, Tokenizer(LANGUAGE))
    except Exception as e:
        return ""
    lemmatizer = WordNetLemmatizer()
    # processed_text = re.sub('[^a-zA-Z]', ' ', parser.document)
    # processed_text = processed_text.lower()
    # processed_text = processed_text.split()
    # processed_text = ' '.join(processed_text)
    tf_idf_model = TfidfVectorizer(max_features=8)
    processed_text_tf = tf_idf_model.fit_transform(str(parser.document).split("."))
    return str(tf_idf_model.get_feature_names())

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
    step_one = feedbacks[1].split('\n')[2]
    step_two = feedbacks[1].split('\n')[3]
    step_three = feedbacks[1].split('\n')[4]
    step_four = feedbacks[1].split('\n')[5]
    step_five = feedbacks[1].split('\n')[6]
    
    return {'response': feedbacks[0], 'query': searchQuery, 'roadmap': feedbacks[1], 'one': step_one, 'two': step_two, 'three': step_three, 'four': step_four, 'five': step_five}