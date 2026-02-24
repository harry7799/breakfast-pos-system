#!/usr/bin/env python3
"""
匯入青青草原廚房完整菜單
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import SessionLocal
from app.models import MenuItem

# 菜單資料
MENU_DATA = {
    "drinks": [
        {"name": "有機蔗糖紅茶", "price": 30},
        {"name": "有機蔗糖紅茶(大)", "price": 35},
        {"name": "三種成份奶茶", "price": 50},
        {"name": "三種成份奶茶(大)", "price": 60},
        {"name": "豆漿(非基改黃豆)", "price": 30},
        {"name": "豆漿紅茶(糖)", "price": 30},
        {"name": "原味冬瓜飲", "price": 35},
        {"name": "冬瓜鳳梨果汁", "price": 55},
        {"name": "冬瓜百香果果汁", "price": 55},
        {"name": "冬瓜檸檬果汁", "price": 55},
        {"name": "有機美式咖啡", "price": 60},
        {"name": "有機美式咖啡(大)", "price": 75},
        {"name": "有機拿鐵(100%奶粉)", "price": 70},
        {"name": "有機拿鐵(100%奶粉)(大)", "price": 85},
        {"name": "生機洛神乾果粒", "price": 50},
        {"name": "100%奶粉", "price": 50},
        {"name": "鳳梨果汁", "price": 55},
        {"name": "百香果果汁", "price": 55},
        {"name": "檸檬果汁", "price": 55},
    ],
    "main_dishes": [
        {"name": "藜麥燉飯-松子粒(素)", "price": 125},
        {"name": "藜麥燉飯-菇菇(素)", "price": 145},
        {"name": "藜麥燉飯-黑豬肉", "price": 145},
        {"name": "藜麥燉飯-菲瑞牛", "price": 145},
        {"name": "藜麥燉飯-花蛤", "price": 150},
        {"name": "藜麥燉飯-炸雞條", "price": 150},
        {"name": "藜麥燉飯-醬燒雞腿", "price": 160},
        {"name": "藜麥燉飯-舒肥雞胸", "price": 160},
        {"name": "義大利麵-松子粒(素)", "price": 125},
        {"name": "義大利麵-菇菇(素)", "price": 145},
        {"name": "義大利麵-黑豬肉", "price": 145},
        {"name": "義大利麵-菲瑞牛", "price": 145},
        {"name": "義大利麵-花蛤", "price": 150},
        {"name": "義大利麵-炸雞條", "price": 150},
        {"name": "義大利麵-醬燒雞腿", "price": 160},
        {"name": "義大利麵-舒肥雞胸", "price": 160},
        {"name": "藜麥白飯-黑豬醬", "price": 90},
        {"name": "藜麥白飯-菇菇(蛋素)", "price": 90},
        {"name": "藜麥白飯-杏鮑菇菇(素)", "price": 90},
        {"name": "藜麥白飯-梅花豬", "price": 90},
        {"name": "藜麥白飯-炸雞條", "price": 95},
        {"name": "藜麥白飯-菲瑞牛", "price": 105},
        {"name": "藜麥白飯-醬燒雞腿", "price": 135},
        {"name": "藜麥白飯-舒肥雞胸", "price": 150},
        {"name": "丼飯-洋蔥醬燒豬", "price": 115},
        {"name": "丼飯-洋蔥醬燒牛肋條", "price": 135},
        {"name": "鍋炒烏龍麵-黑胡椒", "price": 90},
        {"name": "鍋炒烏龍麵-杏鮑菇菇(素)", "price": 100},
        {"name": "鍋炒烏龍麵-黑豬肉", "price": 100},
        {"name": "鍋炒烏龍麵-黑豬肉黑胡椒", "price": 110},
        {"name": "鍋炒烏龍麵-杏鮑菇黑胡椒", "price": 110},
    ],
    "light_meals": [
        {"name": "虎皮蛋捲餅-原味(素)", "price": 50},
        {"name": "虎皮蛋捲餅-玉米(素)", "price": 60},
        {"name": "虎皮蛋捲餅-薯餅(素)", "price": 70},
        {"name": "虎皮蛋捲餅-杏鮑菇(素)", "price": 75},
        {"name": "虎皮蛋捲餅-梅花豬", "price": 75},
        {"name": "虎皮蛋捲餅-菲瑞牛", "price": 80},
        {"name": "虎皮蛋捲餅-鮪魚玉米大板燒", "price": 80},
        {"name": "總匯吐司蛋-玉米(素)", "price": 55},
        {"name": "總匯吐司蛋-薯餅(素)", "price": 65},
        {"name": "總匯吐司蛋-鮪魚玉米", "price": 70},
        {"name": "總匯吐司蛋-杏鮑菇(素)", "price": 75},
        {"name": "總匯吐司蛋-梅花豬", "price": 75},
        {"name": "總匯吐司蛋-菲瑞牛", "price": 80},
        {"name": "總匯吐司蛋-炸雞條", "price": 85},
        {"name": "總匯吐司蛋-舒肥雞胸", "price": 110},
        {"name": "蘿蔔糕X2+煎蛋", "price": 50},
        {"name": "梅花豬蘿蔔糕(蛋)", "price": 85},
        {"name": "菲瑞牛蘿蔔糕(蛋)", "price": 90},
        {"name": "醬燒雞腿蘿蔔糕(蛋)", "price": 115},
        {"name": "舒肥雞胸蘿蔔糕(蛋)", "price": 120},
        {"name": "吉比花生醬吐司(蛋奶素)", "price": 45},
        {"name": "綜合堅果醬吐司(蛋奶素)", "price": 50},
    ],
    "salads": [
        {"name": "高麗菜綜合沙拉-菲瑞牛(蛋)", "price": 160},
        {"name": "高麗菜綜合沙拉-醬燒雞腿(蛋)", "price": 165},
        {"name": "高麗菜綜合沙拉-舒肥雞胸(蛋)", "price": 170},
    ],
    "snacks": [
        {"name": "荷包蛋", "price": 15},
        {"name": "薯餅一片(素)", "price": 25},
        {"name": "地瓜(素)", "price": 45},
        {"name": "有機高麗菜沙拉", "price": 50},
        {"name": "港式蘿蔔糕(葷)", "price": 45},
        {"name": "花蛤湯", "price": 50},
        {"name": "脆薯條", "price": 50},
        {"name": "100%炸雞條", "price": 60},
    ],
}

def main():
    db = SessionLocal()
    try:
        # 清空現有菜單（可選）
        print("清空現有菜單...")
        db.query(MenuItem).delete()
        db.commit()

        # 匯入新菜單
        print("開始匯入菜單...")
        total = 0

        for category, items in MENU_DATA.items():
            for item_data in items:
                menu_item = MenuItem(
                    name=item_data["name"],
                    price=item_data["price"],
                    is_active=True
                )
                db.add(menu_item)
                total += 1

        db.commit()
        print(f"✓ 成功匯入 {total} 個菜單項目")

    except Exception as e:
        print(f"✗ 匯入失敗: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    main()
