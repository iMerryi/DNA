import json
import urllib.request
import urllib.error
import time
import re
from dataclasses import dataclass
from typing import Optional, Callable, Any, List, Tuple

@dataclass
class AIResponse:
    success: bool
    data: Optional[Any] = None
    error_message: str = ""
    tokens_used: int = 0
    duration_seconds: float = 0.0

class OllamaClient:
    def __init__(self, base_url="http://localhost:11434", model_name="modelscope.cn/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF:latest", timeout=300, max_retries=2):
        self.base_url = base_url.rstrip('/')
        self.model_name = model_name
        self.timeout = timeout
        self.max_retries = max_retries

    def test_connection(self) -> Tuple[bool, str]:
        url = f"{self.base_url}/api/tags"
        try:
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    models = [m['name'] for m in data.get('models', [])]
                    model_exists = any("Qwen2.5" in m for m in models)
                    if model_exists:
                        return True, "Ollama服务正常，模型已就绪"
                    else:
                        return False, "Ollama服务正常，但未找到相关Qwen模型，请先执行 ollama pull"
                return False, f"服务响应异常，状态码: {response.status}"
        except Exception as e:
            return False, f"无法连接Ollama服务，请确认服务已启动: {str(e)}"

    def _clean_json_string(self, raw_text: str) -> str:
        try:
            json.loads(raw_text)
            return raw_text
        except json.JSONDecodeError:
            pass
        match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if match:
            return match.group(0)
        return raw_text

    def _stream_request(self, request_body: dict, on_progress: Callable = None, stage_message: str = "AI正在思考...") -> str:
        url = f"{self.base_url}/api/generate"
        data_bytes = json.dumps(request_body).encode('utf-8')
        full_response = ""
        try:
            req = urllib.request.Request(url, data=data_bytes, method='POST')
            req.add_header('Content-Type', 'application/json')
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                chunk_count = 0
                for line in response:
                    if line:
                        chunk = json.loads(line.decode('utf-8'))
                        text_piece = chunk.get("response", "")
                        full_response += text_piece
                        chunk_count += 1
                        if on_progress and chunk_count % 5 == 0: 
                            fake_progress = min(30 + (chunk_count // 10), 80)
                            on_progress(fake_progress, stage_message)
                        if chunk.get("done", False):
                            break
            return full_response
        except Exception as e:
            raise e

    def extract_fields(self, document_text: str, on_progress: Callable = None) -> AIResponse:
        start_time = time.time()
        if on_progress: on_progress(10, "正在组装提取指令...")
        
        system_prompt = """
        你是一个专业的医疗档案信息提取助手。请从用户提供的文本中提取医疗档案信息，并严格以JSON格式输出。
        
        【输出格式要求】
        必须输出且仅输出一个合法的JSON对象，不要包含任何Markdown标记（如```json），不要输出任何解释性文字。结构如下：
        {
          "物理存储": {
            "姓名": "", "性别": "", "出生日期": "", "证件号码": "", "户籍地址": "", 
            "常住地址": "", "建档机构": "", "建档日期": "", "联系电话": "", 
            "民族": "", "ABO血型": "", "Rh血型": "", "父亲姓名": "", "父亲电话": "", 
            "母亲姓名": "", "母亲电话": "", "出生孕周": "", "出生体重": "", "出生身长": "", 
            "分娩机构": "", "Apgar(1min)": "", "Apgar(5min)": "", "档案编号": ""
          },
          "反复存储": [
            {"随访日期": "", "当前体重": "", "体温": ""}
          ],
          "病症记录": {
            "苯丙酮尿症": "", "先天性甲状腺功能减低症": "", "听力筛查": "", 
            "过敏史": "", "先天异常": "", "既往住院史": "", "家族遗传病史": ""
          }
        }
        
        【约束条件】
        1. 性别只能是“男”或“女”。
        2. 如果文本中没有某项信息，请将对应字段的值留空字符串 ""，绝对不要编造。
        3. 如果存在多次随访记录，请全部提取到“反复存储”的数组中；如果没有，保留空数组 []。
        """

        request_body = {
            "model": self.model_name,
            "prompt": document_text,
            "system": system_prompt,
            "stream": True,
            "options": {
                "temperature": 0.1,
                "num_predict": 2048
            }
        }
        
        try:
            if on_progress: on_progress(20, "发送文档给AI分析...")
            raw_output = self._stream_request(request_body, on_progress, "AI正在识别字段...")
            if on_progress: on_progress(90, "正在清洗和解析数据...")
            clean_json_str = self._clean_json_string(raw_output)
            parsed_data = json.loads(clean_json_str)
            if on_progress: on_progress(100, "字段提取完成")
            return AIResponse(success=True, data=parsed_data, duration_seconds=time.time() - start_time)
        except json.JSONDecodeError:
            return AIResponse(success=False, error_message="AI返回格式异常，不是合法JSON", duration_seconds=time.time() - start_time)
        except Exception as e:
            return AIResponse(success=False, error_message=str(e), duration_seconds=time.time() - start_time)

    def correct_errors(self, corrupted_text: str, reference_texts: List[str], on_progress: Callable = None) -> AIResponse:
        start_time = time.time()
        if on_progress: on_progress(10, "正在组装纠错指令...")
        
        ref_str = "\n---\n".join(reference_texts) if reference_texts else "无参考文本"

        system_prompt = f"""
        你是一个DNA解码医疗文本纠错专家。用户在将DNA序列解码为文本时，可能会因为序列损坏产生乱码或错字。
        
        【任务】
        请对比参考文本，找出损坏文本中的错误，进行合理推断并修复，然后严格输出JSON格式结果。
        
        【输出格式要求】
        必须输出且仅输出一个合法的JSON对象，不要包含任何Markdown标记（如```json），不要输出任何解释性文字。结构如下：
        {{
          "corrected_text": "修复后的完整文本",
          "corrections": [
            {{"position": 12, "original": "错字", "corrected": "对字", "reason": "根据上下文推断"}}
          ],
          "confidence": 0.95
        }}
        
        【原则】
        1. 优先参考提供的已知正确数据。
        2. 不要过度修改，如果不确定的字符，保留原文并标注。
        3. 如果损坏文本极其严重无法修复，confidence 低于 0.5，并保留原文。
        """

        user_prompt = f"""
        【损坏文本】
        {corrupted_text}
        
        【参考文本】
        {ref_str}
        """

        request_body = {
            "model": self.model_name,
            "prompt": user_prompt,
            "system": system_prompt,
            "stream": True,
            "options": {
                "temperature": 0.1,
                "num_predict": 2048
            }
        }
        
        try:
            if on_progress: on_progress(20, "发送数据给AI进行纠错对比...")
            raw_output = self._stream_request(request_body, on_progress, "AI正在进行纠错推理...")
            if on_progress: on_progress(90, "正在清洗和解析数据...")
            clean_json_str = self._clean_json_string(raw_output)
            parsed_data = json.loads(clean_json_str)
            if on_progress: on_progress(100, "纠错完成")
            return AIResponse(success=True, data=parsed_data, duration_seconds=time.time() - start_time)
        except json.JSONDecodeError:
            return AIResponse(success=False, error_message="AI返回格式异常，不是合法JSON", duration_seconds=time.time() - start_time)
        except Exception as e:
            return AIResponse(success=False, error_message=str(e), duration_seconds=time.time() - start_time)