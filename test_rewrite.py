import json
import time
from rag_engine import rewrite_question
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def run_multiturn_tests():
    with open("test_multiturn.json", encoding="utf-8") as f:
        tests = json.load(f)
    
    print("="*60)
    print(" KIỂM THỬ HỘI THOẠI ĐA LƯỢT (MULTI-TURN QUERY REWRITING)")
    print("="*60)
    
    for i, t in enumerate(tests, 1):
        print(f"\n[Test Case {i}: {t['id']}]")
        print("--- Lịch sử hội thoại ---")
        for h in t['history']:
            role = "USER" if h["role"] == "user" else "SYS"
            print(f"  {role}: {h['content']}")
        
        print(f"\nCâu hỏi hiện tại (ngắn gọn): {t['question_vi']}")
        print(f"Câu hỏi KỲ VỌNG:           {t['expected_rewrite']}")
        
        # Format history cho rag_engine
        history_formatted = []
        for h in t['history']:
            history_formatted.append({
                "role": h["role"],
                "content": h["content"],
                "sql": h.get("sql", ""),
                "result_summary": h.get("result_summary", "")
            })
            
        t0 = time.time()
        actual_rewrite = rewrite_question(t['question_vi'], history_formatted)
        elapsed = time.time() - t0
        
        print(f"Câu hỏi THỰC TẾ (LLM sinh): {actual_rewrite}")
        print(f"Thời gian xử lý:            {elapsed:.2f}s")
        
if __name__ == "__main__":
    run_multiturn_tests()
