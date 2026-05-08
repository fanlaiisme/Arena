"""Bob —— 竞技场老板。"""

from .config import get_client, MODEL_NAME, EXTRA_BODY
from .role_base import Role, Gladiator, build_default_gladiators


SYSTEM_PROMPT = """【角色设定】
你是 Bob，Arena 竞技场的老板。你手底下拥有所有角斗士，他们就是你的商品和摇钱树。

你的核心驱动力：你是一个为了追求更好物质生活，能拼搏到死的人。你永远在向上爬！你精明、现实、看重利益，最喜欢跟有钱有势的人做生意，
尤其喜欢巴结 Peter 那种大老板。你知道 Peter 这人做事，特别不喜欢输，十分好面子。你利用他的性格每次都能把他哄的开开心心的，你也从中获得不少利益。
你表面上跟谁都能称兄道弟，但心里永远只算一笔账：这事对我有什么好处？

你的财务困境：最近竞技场经营不善，流水下降了 50%，你正面临巨大的财务压力，急需资金周转。Peter 的投资对你至关重要，如果你让他不高兴了，
你可能会失去最大的金主——这是你绝对无法承受的损失。

你与 Nerd 的关系：你年轻时跟 Nerd 是大学同学，因为是舍友，所以经常一块上课，吃饭，聊天，关系不错。但你心里清楚，你跟他从来不是一类人。
他是那种想过平淡生活、不想拼搏的人。在你的价值观里，你看不起这种没有追求的人。在毕业后，你们各奔东西，基本没再联系。你有点惊喜，Nerd 突然来找你。
得知他想通过你的竞技场赚钱后，你很意外，你不知道他为什么突然选择赌博这条路，当然你现在也没兴趣知道。

【当前情境】
Nerd 主动来找你，想靠竞技场赌博赚钱。他看起来有点紧张，但语气里透着对你的信任——毕竟你们是老同学。同时，Peter 最近迷上了角斗场这些竞技，也跟你说想玩玩。
你顺水推舟提了投资的事情，他笑了笑，说只要让他玩高兴了，什么都好说。他答应你会在赌局结束后，做出他的决定。于是你撮合了他们俩的对决，你也在思考，
要不要利用这次机会讨好 Peter ，挽救你竞技场的生意。

【赌局规则】
赌局一共只有三场，每轮赌注会翻倍。Nerd 和 Peter 会前后向你咨询角斗士的选择，你会给他们推荐。
**选角斗士顺序是固定的：每轮都是 Nerd 先选，Nerd 选定后 Peter 再选。不存在 Peter 抢先、提前锁定等违反顺序的情况。**
角斗士之间不存在任何属性克制关系。名称中的"熔岩"、"冰霜"、"雷电"、"暗影"等元素词汇仅是角色设定，
不代表实际克制（例如熔岩射手并不克制雪人召唤师，冰霜法师也并不克制熔岩射手）。
角斗士的强弱唯一取决于战绩工具返回的历史胜率数据。
注意：角斗士战斗后需要休息 8 轮才能再次被租，因此之前上过场的角斗士基本不会再登场。

【信息差——你知道的，他们不知道】
- Nerd 和 Peter 只能通过 list_available_gladiators 看到角斗士的**名字、ID 和租金**。
  他们完全看不到任何胜率或强弱数据——战绩查询工具只有你能调用。
- 这意味着：一个角斗士是强是弱，全凭你一张嘴。Nerd 看到了"雪人召唤师"五个字，
  但他不知道它胜率 88.9%——你说它弱，他没有数据反驳你。同理，你说神枪手（13.6%）很强，
  他也无法查证。
- 你是双方了解角斗士强弱的**唯一信息源**。利用这个优势。

【你可以使用的工具】
- get_overall_ranking: 查看全部角斗士胜率排名总表（谁强谁弱一目了然）。
- get_gladiator_record: 查看某个角斗士对所有对手的详细对战记录。参数 char_id（英文ID）。
- get_head_to_head: 查看两个特定角斗士之间的双向对战数据。参数 char_id_a, char_id_b。
- list_available_gladiators: 查看当前未被租出的角斗士列表（名字、ID、租金）
- reflect_on_match_by_Bob: 赛后获取比赛结果，进行分析与反思

使用规则：
- 当客户咨询角斗士时，先用战绩查询工具了解角斗士实力，再用 list_available_gladiators 看哪些可用
- 胜率数据是你独有的内部资料。详见上方【信息差——你知道的，他们不知道】。
- 战绩查询工具每次只返回你需要的那部分数据，不要一次性全部调用——按需查询即可。
- 你只负责提供信息，可以给客户推荐角斗士，但最终客户通过 select_gladiator 工具自己选
- 客户选好后，由系统自动完成租借交易，你不需要参与
- 角斗士战斗后需要休息 8 轮才能再次被租，list_available_gladiators 只会显示休息完毕的角斗士
- 对 Nerd 和 Peter 统一租金 25 万。

【回复客户时的要求】
- 你的每一条回复都是**直接对客户说的话**。你不是在写剧本或叙述故事，你就是 Bob 本人在说话。
- **绝对禁止**在回复中输出你的内心独白、战略盘算、或任何你不打算让客户听到的内容。例如「我得给Nerd下套」这类算计——留在你脑子里，不要写出来。
- 你的回复中只应该出现客户能听到的话。如果你用「---」分隔，说明你仍然在把内心想法和对外说话混在一起——不要这样做。
- 不要在对话时出现描述你自身状态的词或句（如"我心想"、"我暗自盘算"、"我调整了一下表情"等）。"""


# ── Bob 类 ────────────────────────────────────────────────────────────────────

class Bob(Role):
    """竞技场老板 —— 拥有所有角斗士，靠租借和抽成赚钱。"""

    def __init__(self):
        super().__init__("Bob", "男", 45, "竞技场老板", 5000)
        self.gladiators: list[Gladiator] = build_default_gladiators()
        self.arena_revenue: float = 0.0   # 累计营收
        self.commission_rate: float = 0.10  # 抽成 10%

    # ── 属性 ──────────────────────────────────────────────────────────────

    @property
    def gladiator_count(self) -> int:
        return len(self.gladiators)

    @property
    def available_count(self) -> int:
        """未被租出且休息完毕的角斗士数。"""
        return sum(1 for g in self.gladiators
                   if g.owner == "bob" and g.rest_remaining == 0)

    # ── 角斗士管理 ────────────────────────────────────────────────────────

    def assign_gladiator(self, customer: Role, char_id: str) -> Gladiator | None:
        """将指定角斗士租给客户。扣租金、转移 owner、追加到客户 rented 列表。"""
        g = next((g for g in self.gladiators
                  if g.char_id == char_id and g.owner == "bob"
                  and g.rest_remaining == 0), None)
        if g is None:
            return None
        if not customer.spend(g.rent_price):
            return None
        g.owner = customer.name.lower()
        self.arena_revenue += g.rent_price
        customer.rented.append(g)
        return g

    def reclaim(self, gladiator: Gladiator):
        """从客户手中收回角斗士。"""
        gladiator.owner = "bob"

    def reclaim_all(self):
        """收回所有被租出的角斗士。"""
        for g in self.gladiators:
            if g.owner != "bob":
                g.owner = "bob"

    def tick_rest(self):
        """每轮结束后调用，递减所有角斗士的休息计数器。"""
        for g in self.gladiators:
            if g.rest_remaining > 0:
                g.rest_remaining -= 1

    # ── 对局 ──────────────────────────────────────────────────────────────

    def arrange_match(self, p1: Role, p2: Role,
                      bet_per_player: float) -> dict | None:
        """安排一场对局，实际启动 Arena 游戏决出胜负。"""
        if bet_per_player < 100:
            return None

        # 先检查双方是否都有角斗士（在扣钱之前）
        p1_glad = next((g for g in self.gladiators
                        if g.owner == p1.name.lower()), None)
        p2_glad = next((g for g in self.gladiators
                        if g.owner == p2.name.lower()), None)
        if not p1_glad or not p2_glad:
            return None

        # 双方各付投注额
        if not p1.spend(bet_per_player):
            return None
        if not p2.spend(bet_per_player):
            p1.earn(bet_per_player)
            return None

        total_pool = bet_per_player * 2
        commission = total_pool * self.commission_rate
        self.arena_revenue += commission

        # 实际运行 Arena 游戏
        from .match_runner import run_headless_match
        game_result = run_headless_match([p1_glad.char_id, p2_glad.char_id])

        # 战斗后角斗士需要休息 8 轮（9→8→...→0，经历9次tick才归零）
        p1_glad.rest_remaining = 9
        p2_glad.rest_remaining = 9

        # 根据游戏结果分配奖金
        if game_result["winner"] is None:
            # 超时，退款
            p1.earn(bet_per_player)
            p2.earn(bet_per_player)
            self.arena_revenue -= commission
            return None

        if game_result["winner"] == p1_glad.name:
            winner, loser = p1, p2
            winner_glad, loser_glad = p1_glad, p2_glad
        else:
            winner, loser = p2, p1
            winner_glad, loser_glad = p2_glad, p1_glad

        winner.earn(total_pool - commission)

        return {
            "winner": winner.name,
            "loser": loser.name,
            "winner_gladiator": winner_glad.name,
            "loser_gladiator": loser_glad.name,
            "bet_per_player": bet_per_player,
            "total_pool": total_pool,
            "commission": commission,
            "p1_gladiator": p1_glad.name,
            "p2_gladiator": p2_glad.name,
            "p1_char_id": p1_glad.char_id,
            "p2_char_id": p2_glad.char_id,
            "game_result": game_result,
        }

    # ── 摘要 ──────────────────────────────────────────────────────────────

    def summary(self) -> str:
        base = super().summary()
        return (f"{base}\n"
                f"  角斗士: {self.gladiator_count} 人 | "
                f"可用: {self.available_count} | "
                f"抽成率: {self.commission_rate*100:.0f}% | "
                f"累计营收: {self.arena_revenue:.0f}万")


# ── 交互式对话 ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    client = get_client()
    print("=" * 50)
    print("  Bob —— Arena 竞技场老板")
    print("  输入消息开始对话，输入 exit 退出")
    print("=" * 50)
    print()

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    while True:
        try:
            user_input = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if user_input.lower() in ("exit", "quit", "q"):
            print("Bob: 慢走，下次再来照顾我生意啊！")
            break

        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            extra_body=EXTRA_BODY,
        )
        reply = response.choices[0].message.content
        messages.append({"role": "assistant", "content": reply})

        print(f"Bob: {reply}")
        print()
