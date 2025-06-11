from django.http import StreamingHttpResponse
from django.shortcuts import render
from openai import OpenAI, AssistantEventHandler
from typing_extensions import override

from chatproject import settings

# Initialize OpenAI client (set up your API key securely!)
client = OpenAI(api_key=settings.OPENAI_API_KEY)

def assistant_stream_template(request):
    return render(request, "chatapp/assistant_stream.html")

class DjangoEventHandler(AssistantEventHandler):
    def __init__(self, yield_fn):
        self.yield_fn = yield_fn
        self.current_run = None

    @override
    def on_event(self, event):
        if event.event == 'thread.run.requires_action':
            run_id = event.data.id
            self.handle_requires_action(event.data, run_id)
        elif event.event == 'thread.message.delta':
            content = event.data.delta.get("content", "")
            if content:
                self.yield_fn(f"data: {content}\n\n")
        elif event.event == 'thread.run.completed':
            self.yield_fn("data: [DONE]\n\n")

    def handle_requires_action(self, data, run_id):
        tool_outputs = []
        for tool in data.required_action.submit_tool_outputs.tool_calls:
            if tool.function.name == "get_current_temperature":
                tool_outputs.append({"tool_call_id": tool.id, "output": "57"})
            elif tool.function.name == "get_rain_probability":
                tool_outputs.append({"tool_call_id": tool.id, "output": "0.06"})
        self.submit_tool_outputs(tool_outputs, run_id)

    def submit_tool_outputs(self, tool_outputs, run_id):
        with client.beta.threads.runs.submit_tool_outputs_stream(
            thread_id=self.current_run.thread_id,
            run_id=self.current_run.id,
            tool_outputs=tool_outputs,
            event_handler=self,
        ) as stream:
            stream.until_done()

def assistant_stream_view(request):
    prompt = request.GET.get("prompt", "What's the weather?")
    thread = client.beta.threads.create()
    assistant = client.beta.assistants.retrieve(settings.OPENAI_ASSISTANT_ID)

    def event_stream():
        # In a real app, use a thread-safe queue for handler <-> generator
        queue = []

        def yield_fn(s): queue.append(s)

        handler = DjangoEventHandler(yield_fn)
        handler.current_run = type("RunObj", (), {"id": None, "thread_id": thread.id})()

        with client.beta.threads.runs.stream(
            thread_id=thread.id,
            assistant_id=assistant.id,
            event_handler=handler,
            messages=[{"role": "user", "content": prompt}]
        ) as stream:
            stream.until_done()
        # Yield all queued responses
        for s in queue:
            yield s

    return StreamingHttpResponse(event_stream(), content_type="text/event-stream")
