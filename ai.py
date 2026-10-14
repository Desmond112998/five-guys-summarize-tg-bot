# ai.py

import requests  # Use requests for synchronous HTTP calls
import base64
import json
from openai import OpenAI, APITimeoutError  # Use the synchronous OpenAI client
from config import (
    API_KEY,
    BASE_URL,
    MODEL,
    AI_GENERATE_BASE_PROMPT,
    LOVE_SYSTEM_PROMPT,
    AI_ANSWER_SYSTEM_PROMPT,
    SERPER_API_KEY,
    logger,
)

# --- CLIENT INITIALIZATION ---
client = OpenAI(api_key=API_KEY, base_url=BASE_URL)


# --- SERPER SEARCH FUNCTION ---
def search_with_serper(query: str, time_range: str = "qdr:y") -> str:
    """
    Search for information using Serper.dev API.

    Args:
        query: The search query
        time_range: Time range for results. Options:
            - "qdr:h" - past hour
            - "qdr:d" - past 24 hours (for real-time info like weather, news)
            - "qdr:w" - past week
            - "qdr:m" - past month
            - "qdr:y" - past year (default for general queries)

    Returns:
        Formatted search results as a string
    """
    try:
        logger.info(f"Searching with Serper: {query} (time_range: {time_range})")

        url = "https://google.serper.dev/search"
        payload = json.dumps(
            {
                "q": query,
                "num": 10,  # Get top 10 results
                "location": "Hong Kong",  # Get results from Hong Kong
                "gl": "hk",  # Get results from Hong Kong
                "hl": "zh-tw",  # Get results in Chinese
                "tbs": time_range,  # Time-based search
            }
        )
        headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}

        response = requests.post(url, headers=headers, data=payload, timeout=10)
        response.raise_for_status()

        data = response.json()
        logger.info("Serper search successful")

        # Format the search results
        search_results = []

        # Add organic results
        if "organic" in data:
            for idx, result in enumerate(data["organic"][:5], 1):
                title = result.get("title", "")
                snippet = result.get("snippet", "")
                link = result.get("link", "")
                search_results.append(f"{idx}. {title}\n   {snippet}\n   來源: {link}")

        # Add knowledge graph if available
        if "knowledgeGraph" in data:
            kg = data["knowledgeGraph"]
            kg_title = kg.get("title", "")
            kg_desc = kg.get("description", "")
            if kg_title and kg_desc:
                search_results.insert(0, f"📚 知識圖譜: {kg_title}\n   {kg_desc}\n")

        if search_results:
            return "\n\n".join(search_results)
        else:
            return "搵唔到相關資料"

    except requests.exceptions.Timeout:
        logger.error("Serper API timeout")
        return "搜尋超時，請再試一次"
    except requests.exceptions.RequestException as e:
        logger.error(f"Serper API error: {e}")
        return "搜尋出現問題，請再試一次"
    except Exception as e:
        logger.error(f"Unexpected error in search_with_serper: {e}")
        return "搜尋系統出錯"


# --- VISION FUNCTION (SYNCHRONOUS) ---
def get_ai_vision_response(user_prompt: str, image_url: str, system_prompt: str) -> str:
    """
    Generates a response from the AI based on a text prompt and an image using synchronous calls.
    Includes enhanced logging to inspect the full API response.
    """
    logger.info("Starting get_ai_vision_response function.")
    try:
        logger.info(f"Downloading image from URL: {image_url}")
        response = requests.get(image_url, timeout=15)
        response.raise_for_status()
        image_bytes = response.content
        logger.info("Image downloaded successfully.")

        logger.info("Encoding image to Base64.")
        base64_image = base64.b64encode(image_bytes).decode("utf-8")
        logger.info("Image encoded successfully.")

        logger.info("Calling OpenAI API for vision response.")
        api_response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            },
                        },
                    ],
                },
            ],
            stream=False,
        )

        # --- NEW DEBUGGING LINES ---
        # Log the full, raw response object from the API to see its structure.
        logger.info(f"Full API Response: {api_response}")

        # Check if the response is valid before trying to access its content.
        if api_response.choices and api_response.choices[0].message:
            logger.info("OpenAI API call successful, content found.")
            return api_response.choices[0].message.content
        else:
            # This will now catch cases where the API returns 200 OK but an empty/filtered response.
            logger.error("API call was successful but returned no content/choices.")
            return "AI 成功回應，但內容係空嘅，可能係安全設定擋咗。"

    except requests.exceptions.Timeout:
        logger.error("Timeout occurred while downloading image.")
        return "下載圖片超時，張相可能太大或者網絡有問題"
    except requests.exceptions.RequestException as http_err:
        logger.error(f"HTTP error occurred while downloading image: {http_err}")
        return "下載唔到張圖，請再試一次"
    except APITimeoutError:
        logger.error("OpenAI API call timed out.")
        return "AI諗太耐諗到瞓著咗，請再試一次"
    except Exception as e:
        logger.error(f"An unexpected error occurred in get_ai_vision_response: {e}")
        # Log the actual API response object if an error occurs during parsing
        if "api_response" in locals():
            logger.error(
                f"API response at time of error: {locals().get('api_response')}"
            )
        return "系統分析唔到張圖，好對唔住"


# --- FUNCTION TOOLS DEFINITION ---
SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_with_serper",
        "description": """搜尋網上最新資料。當用戶問題涉及以下情況時應該使用此工具：
- 實時資訊：天氣、新聞、股價、匯率等
- 最新數據：當前價格、今日資訊、最近消息
- 事實查證：需要驗證嘅資料、統計數字
- 你知識庫以外嘅資訊：2024年後嘅資料、最新發展

不需要搜尋嘅情況：
- 基本概念解釋（例如：點解天空係藍色）
- 歷史事件、科學原理
- 純粹意見、建議類問題

⚠️ 時間邏輯檢查：
如果搜尋結果中嘅日期同用戶提供嘅當前日期有矛盾（例如：搜尋結果話「預計10月1日」但而家已經10月10日），你應該：
1. 再次搜尋更新資訊（用更具體嘅關鍵詞 + qdr:d）
2. 或者喺回答中說明呢個時間差異""",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜尋查詢字串，應該簡潔且準確。例如：'香港天氣 2025年10月10日'、'比特幣價格'、'香港最低工資 2024'",
                },
                "time_range": {
                    "type": "string",
                    "enum": ["qdr:h", "qdr:d", "qdr:w", "qdr:m", "qdr:y"],
                    "description": """搜尋時間範圍：
- 'qdr:h': 過去1小時（極度實時資訊）
- 'qdr:d': 過去24小時（天氣、今日新聞、當日股價）
- 'qdr:w': 過去1星期（最近新聞、短期趨勢）
- 'qdr:m': 過去1個月（近期發展）
- 'qdr:y': 過去1年（一般查詢，預設值）

選擇建議：
- 天氣、今日新聞 → qdr:d
- 即時股價、匯率 → qdr:h 或 qdr:d
- 最近政策、趨勢 → qdr:m
- 一般知識、非時效性資訊 → qdr:y""",
                    "default": "qdr:y",
                },
            },
            "required": ["query"],
        },
    },
}


# --- TEXT-ONLY FUNCTIONS (SYNCHRONOUS) ---
def get_ai_answer_with_tools(
    user_prompt: str = None,
    max_iterations: int = 3,
    history_messages: list = None,
) -> str:
    """
    Generates a text-based answer from the AI with tool calling capability.
    AI can decide whether to search for information using Serper.
    Supports iterative tool calling - AI can search, analyze results, and search again if needed.

    Args:
        user_prompt: The user's question (legacy single-turn)
        max_iterations: Maximum number of tool calling iterations (default: 3)
        history_messages: Optional prior turns as {role, content}; current user turn last
    """
    try:
        if history_messages:
            logger.info(
                f"Starting get_ai_answer_with_tools with {len(history_messages)} history message(s)"
            )
            messages = [
                {"role": "system", "content": AI_ANSWER_SYSTEM_PROMPT},
                *history_messages,
            ]
        else:
            logger.info(f"Starting get_ai_answer_with_tools for prompt: {user_prompt}")
            messages = [
                {"role": "system", "content": AI_ANSWER_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]

        iteration = 0
        while iteration < max_iterations:
            iteration += 1
            logger.info(f"Tool calling iteration {iteration}/{max_iterations}")

            # Call AI - may decide to use tools
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=[SEARCH_TOOL],
                tool_choice="auto",  # Let AI decide
                stream=False,
            )

            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls

            # If AI wants to use tools
            if tool_calls:
                logger.info(
                    f"AI requested {len(tool_calls)} tool call(s) in iteration {iteration}"
                )

                # Add AI's response to messages
                messages.append(response_message)

                # Execute each tool call
                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)

                    logger.info(f"Calling {function_name} with args: {function_args}")

                    if function_name == "search_with_serper":
                        query = function_args.get("query")
                        time_range = function_args.get("time_range", "qdr:y")

                        # Call the search function
                        search_results = search_with_serper(query, time_range)

                        # Add function result to messages
                        messages.append(
                            {
                                "tool_call_id": tool_call.id,
                                "role": "tool",
                                "name": function_name,
                                "content": search_results,
                            }
                        )

                # Continue loop - AI will process results and may call tools again
                continue

            else:
                # AI decided it has enough information, return final answer
                logger.info(f"AI provided final answer after {iteration} iteration(s)")
                return response_message.content

        # Max iterations reached, return whatever AI has
        logger.warning(f"Max iterations ({max_iterations}) reached")
        return (
            response_message.content
            if response_message.content
            else "系統處理超時，請簡化問題再試"
        )

    except Exception as e:
        logger.error(f"Error in get_ai_answer_with_tools: {e}")
        return "系統想方加(出錯)，好對唔住"


def get_ai_answer(user_prompt: str, search_results: str = None) -> str:
    """
    Generates a text-based answer from the AI.
    If search_results are provided, they will be included in the prompt.

    Note: This is the legacy function. Use get_ai_answer_with_tools() for automatic tool calling.
    """
    try:
        # If search results are provided, include them in the prompt
        if search_results:
            enhanced_prompt = f"""用戶問題：{user_prompt}

以下係網上搜尋到嘅最新相關資料（僅供參考）：
{search_results}

---

請結合你嘅知識庫同上述搜尋資料，經過分析同思考後，用廣東話回答用戶嘅問題。

重要提示：
- 搜尋資料只係參考材料，唔係要你照抄
- 運用你嘅知識去理解、分析、補充搜尋結果
- 提供有見地嘅答案，唔係單純轉述資料
- 如用咗搜尋資料，可簡單註明「根據最新資料」"""
        else:
            enhanced_prompt = user_prompt

        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": AI_ANSWER_SYSTEM_PROMPT},
                {"role": "user", "content": enhanced_prompt},
            ],
            stream=False,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error in get_ai_answer: {e}")
        return "系統想方加(出錯)，好對唔住"


def get_ai_summary(user_prompt: str, system_prompt="") -> str:
    """
    Generates a text-based summary or response from the AI.
    """
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        system_prompt if system_prompt else AI_GENERATE_BASE_PROMPT
                    ),
                },
                {"role": "user", "content": user_prompt},
            ],
            stream=False,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error in get_ai_summary: {e}")
        return "系統想方加(出錯)，好對唔住"


def get_ai_chat_response(system_prompt: str, history_messages: list) -> str:
    """
    Open chat reply using an explicit conversation history (user/assistant turns).
    """
    try:
        messages = [
            {"role": "system", "content": system_prompt},
            *history_messages,
        ]
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            stream=False,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Error in get_ai_chat_response: {e}")
        return "系統想方加(出錯)，好對唔住"


def get_ai_apology() -> str:
    """
    Generates a humorous apology.
    """
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "user",
                    "content": "用繁體中文同香港式口語去道歉，請人食五仁月餅，搞笑但唔會得罪人嘅道歉，要有啲emoji，字數30以下，不用加上註解",
                },
            ],
            stream=False,
        )
        apology = response.choices[0].message.content
        apology += "\n\n免責聲明: 唔關五仁月餅事🥮求下大家俾下面🙏"
        return apology
    except Exception as e:
        print(f"Error in get_ai_apology: {e}")
        return "哎呀，道歉失敗，唔好打我🙏"


def get_ai_love_quote(username: str, user_messages: str) -> str:
    """
    Generates a cheesy love quote.
    """
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": LOVE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"username:{username}\tuser's messages:{user_messages}",
                },
            ],
            stream=False,
        )
        love_quote = response.choices[0].message.content
        love_quote += "\n\n免責聲明: 土味情話純屬娛樂😘請勿當真💖"
        return love_quote
    except Exception as e:
        print(f"Error in get_love_quote: {e}")
        return "哎呀，情話生成失敗，愛你唔使講😜"


def get_ai_countdown(user_prompt="") -> str:
    """
    Generates a creative countdown message.
    """
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": AI_GENERATE_BASE_PROMPT},
                {
                    "role": "user",
                    "content": f"再修飾以下句子，使內容變得有趣: '{user_prompt}'",
                },
            ],
            stream=False,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error in get_ai_countdown: {e}")
        return f"錯撚曬！"
