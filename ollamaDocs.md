Ollama Python Library
The Ollama Python library provides the easiest way to integrate Python 3.8+ projects with Ollama.

Prerequisites
Ollama should be installed and running
Pull a model to use with the library: ollama pull <model> e.g. ollama pull llama3.2
See Ollama.com for more information on the models available.
Install
pip install ollama
Usage
from ollama import chat
from ollama import ChatResponse

response: ChatResponse = chat(model='llama3.2', messages=[
  {
    'role': 'user',
    'content': 'Why is the sky blue?',
  },
])
print(response['message']['content'])
# or access fields directly from the response object
print(response.message.content)
See _types.py for more information on the response types.

Streaming responses
Response streaming can be enabled by setting stream=True.

from ollama import chat

stream = chat(
    model='llama3.2',
    messages=[{'role': 'user', 'content': 'Why is the sky blue?'}],
    stream=True,
)

for chunk in stream:
  print(chunk['message']['content'], end='', flush=True)
Custom client
A custom client can be created by instantiating Client or AsyncClient from ollama.

All extra keyword arguments are passed into the httpx.Client.

from ollama import Client
client = Client(
  host='http://localhost:11434',
  headers={'x-some-header': 'some-value'}
)
response = client.chat(model='llama3.2', messages=[
  {
    'role': 'user',
    'content': 'Why is the sky blue?',
  },
])
Async client
The AsyncClient class is used to make asynchronous requests. It can be configured with the same fields as the Client class.

import asyncio
from ollama import AsyncClient

async def chat():
  message = {'role': 'user', 'content': 'Why is the sky blue?'}
  response = await AsyncClient().chat(model='llama3.2', messages=[message])

asyncio.run(chat())
Setting stream=True modifies functions to return a Python asynchronous generator:

import asyncio
from ollama import AsyncClient

async def chat():
  message = {'role': 'user', 'content': 'Why is the sky blue?'}
  async for part in await AsyncClient().chat(model='llama3.2', messages=[message], stream=True):
    print(part['message']['content'], end='', flush=True)

asyncio.run(chat())
API
The Ollama Python library's API is designed around the Ollama REST API

Chat
ollama.chat(model='llama3.2', messages=[{'role': 'user', 'content': 'Why is the sky blue?'}])
Generate
ollama.generate(model='llama3.2', prompt='Why is the sky blue?')
List
ollama.list()
Show
ollama.show('llama3.2')
Create
ollama.create(model='example', from_='llama3.2', system="You are Mario from Super Mario Bros.")
Copy
ollama.copy('llama3.2', 'user/llama3.2')
Delete
ollama.delete('llama3.2')
Pull
ollama.pull('llama3.2')
Push
ollama.push('user/llama3.2')
Embed
ollama.embed(model='llama3.2', input='The sky is blue because of rayleigh scattering')
Embed (batch)
ollama.embed(model='llama3.2', input=['The sky is blue because of rayleigh scattering', 'Grass is green because of chlorophyll'])
Ps
ollama.ps()
Errors
Errors are raised if requests return an error status or if an error is detected while streaming.

model = 'does-not-yet-exist'

try:
  ollama.chat(model)
except ollama.ResponseError as e:
  print('Error:', e.error)
  if e.status_code == 404:
    ollama.pull(model)