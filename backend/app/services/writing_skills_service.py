from __future__ import annotations

from typing import Any, Optional
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.writing_skill import SkillExecution, WritingSkill
from ..repositories.novel_repository import NovelRepository
from .llm_service import LLMService


SKILL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "id": "scene-conflict-booster",
        "name": "场景冲突强化",
        "description": "聚焦当前场景的阻力、选择与代价，给出可直接用于改写的强化建议。",
        "overview": "适合在章节已经写完但场面不够抓人时使用，帮你把目标、阻碍、代价和抉择重新拉到台前。",
        "category": "情节",
        "author": "玄穹文枢",
        "version": "0.1.0",
        "source_url": None,
        "use_cases": [
            "角色推进剧情时显得过于顺利",
            "冲突存在，但读者感受不到压迫感",
            "想把静态对话场景改得更有张力",
        ],
        "input_guide": "写清这一场的目标、阻碍和你担心不够强的地方，例如“检查这一章主角和掌柜谈判的冲突是否太弱”。",
        "output_format": ["问题判断", "3 条强化建议", "必要时给出一小段示例改写"],
        "tips": [
            "如果已经绑定项目与章节，技能会自动参考当前章节正文。",
            "输入里最好补一句你最想强化的冲突类型，例如利益冲突、情绪冲突、信息冲突。",
        ],
        "example_prompt": "检查这一章审讯戏的冲突是否太平，并给出 3 条能直接改写进正文的强化建议。",
        "tags": ["场景", "冲突", "改写"],
        "instruction_template": "请聚焦场景中的目标、阻力、代价与选择，给出3条可直接改写的强化建议。",
    },
    {
        "id": "character-voice-polisher",
        "name": "角色声音校准",
        "description": "检查对白是否贴合角色身份、关系与情绪状态。",
        "overview": "适合处理“角色说话都像一个人”的问题，帮助区分身份、性格、情绪和关系带来的语气差异。",
        "category": "角色",
        "author": "玄穹文枢",
        "version": "0.1.0",
        "source_url": None,
        "use_cases": [
            "人物对白辨识度不够",
            "角色在高压情境下说话仍过于平静或统一",
            "想让主角、反派、配角的语言风格更分明",
        ],
        "input_guide": "告诉技能你重点担心哪位角色的声音失真，或直接要求比较两名角色的对白差异。",
        "output_format": ["声音失真判断", "3 条替换建议", "必要时给出示例对白"],
        "tips": [
            "补充角色身份、年龄、阶层、教育背景，会让建议更准。",
            "如果这一章存在强情绪冲突，最好说明角色此刻的情绪状态。",
        ],
        "example_prompt": "检查女主和军师在这一章里的对白是否说得太像同一种人，并给出替换建议。",
        "tags": ["角色", "对白", "语气"],
        "instruction_template": "请检查角色对白/叙述声音是否贴合身份、情绪与关系，并给出3条可直接替换或重写的建议。",
    },
    {
        "id": "clue-layout-checker",
        "name": "线索布局检查",
        "description": "检查伏笔、误导和回收点是否足够清晰，适合推理章节。",
        "overview": "适合在推理、悬疑和信息博弈型章节中使用，帮助你判断线索是否埋得太浅、太显眼或回收不够稳。",
        "category": "推理",
        "author": "玄穹文枢",
        "version": "0.1.0",
        "source_url": None,
        "use_cases": [
            "推理章节的线索散乱或不成链",
            "担心误导线索过弱、过强或过于刻意",
            "想检查伏笔是否具备后续回收空间",
        ],
        "input_guide": "说明你想检查的是本章线索、整段案件链条，还是某个关键伏笔是否成立。",
        "output_format": ["线索问题判断", "3 条布局建议", "必要时给出伏笔补写示例"],
        "tips": [
            "如果项目已有章节摘要或角色关系，技能会参考上下文判断线索是否自洽。",
            "可以直接点名你担心的“凶手线”“假线索”或“回收点”。",
        ],
        "example_prompt": "检查这一章密室案里的误导线索是否太刻意，并给出可执行的调整建议。",
        "tags": ["推理", "伏笔", "线索"],
        "instruction_template": "请检查线索铺设、误导与回收是否清晰，指出问题并给出3条可执行修改建议。",
    },
    {
        "id": "pacing-rhythm-tuner",
        "name": "章节节奏调谐",
        "description": "检查信息推进、场景切换与情绪起伏，避免章节过慢或过赶。",
        "overview": "适合章节写完后整体审视节奏，判断哪里拖沓、哪里跳太快，以及信息爆点是否放在对的位置。",
        "category": "节奏",
        "author": "玄穹文枢",
        "version": "0.1.0",
        "source_url": None,
        "use_cases": [
            "中段推进慢，读起来发闷",
            "高潮前铺垫不足或过量",
            "章节切换频繁但情绪线不顺",
        ],
        "input_guide": "说明你想优化整章节奏，还是某一段的推进速度；也可以指出“前半段太慢”这类直觉问题。",
        "output_format": ["节奏诊断", "3 条调速建议", "必要时给出重排方案"],
        "tips": [
            "如果你能指出“读起来卡住”的段落位置，建议会更聚焦。",
            "适合在大改前先跑一次，确定删减和扩写优先级。",
        ],
        "example_prompt": "检查这一章前半段是否铺垫过长、后半段是否推进过快，并给出调速方案。",
        "tags": ["节奏", "章节", "结构"],
        "instruction_template": "请检查章节节奏、信息推进和情绪起伏是否平衡，指出最拖沓或最仓促的部分，并给出3条可执行调整建议。",
    },
    {
        "id": "show-dont-tell-rewriter",
        "name": "展示感改写器",
        "description": "把直说式叙述改成可被读者看见、听见、感到的场景表达。",
        "overview": "适合处理“作者在解释，而不是角色在经历”的段落，把抽象说明转成可感知的动作、细节与反应。",
        "category": "叙述",
        "author": "玄穹文枢",
        "version": "0.1.0",
        "source_url": None,
        "use_cases": [
            "大段概述太多，读者代入感弱",
            "情绪描写直接说结论，缺少过程",
            "想把信息说明改成场景化表达",
        ],
        "input_guide": "直接指出哪一段“太像总结/解释”，或要求技能专门改写情绪、动作、环境感知。",
        "output_format": ["直说问题判断", "3 条展示化建议", "必要时给出示例改写"],
        "tips": [
            "如果你想保留原句信息量，可以在输入里说明“不要删信息，只换表达方式”。",
            "适合和“语言清晰度”技能配合使用。",
        ],
        "example_prompt": "把这一章里直接说明角色害怕的写法改成更有画面感的展示方式。",
        "tags": ["叙述", "改写", "画面感"],
        "instruction_template": "请找出文本里过于直说、解释化的地方，把它改成更具画面感和感官体验的表达，并给出3条具体建议。",
    },
    {
        "id": "dialogue-subtext-enhancer",
        "name": "对白潜台词增强",
        "description": "强化对白中的试探、遮掩、压迫与关系张力，让话里有话。",
        "overview": "适合谈判、审讯、暧昧、对峙等场面，帮助对白不只传递信息，还传递权力关系和情绪波动。",
        "category": "对白",
        "author": "玄穹文枢",
        "version": "0.1.0",
        "source_url": None,
        "use_cases": [
            "对白只在交换信息，没有暗流",
            "角色关系很复杂，但台词不体现微妙变化",
            "想让审讯、博弈、暧昧戏更有张力",
        ],
        "input_guide": "说明这场对白的关系底色，例如试探、隐瞒、逼供、示弱或暧昧，这会显著提升建议质量。",
        "output_format": ["潜台词问题判断", "3 条对白增强建议", "必要时给出示例对白"],
        "tips": [
            "如果点名双方角色，技能会更容易对准语言权力关系。",
            "适合对白已经成形，但想再拉高层次时使用。",
        ],
        "example_prompt": "让这一段师徒对话更有试探和压迫感，不要只是把情报说出来。",
        "tags": ["对白", "潜台词", "张力"],
        "instruction_template": "请检查对白是否缺少潜台词、权力关系和情绪暗流，并给出3条可直接替换或补强的对白建议。",
    },
    {
        "id": "chapter-hook-designer",
        "name": "章首抓钩设计",
        "description": "检查开场是否足够抓人，并给出更能吸引继续读下去的切入方式。",
        "overview": "适合新章节开头、转场后首段和连载更新开篇，用来提高进入速度和读者的继续阅读意愿。",
        "category": "结构",
        "author": "玄穹文枢",
        "version": "0.1.0",
        "source_url": None,
        "use_cases": [
            "章首太平，没有立即抓住读者",
            "新场景切入过慢，信息前戏过长",
            "连载章节需要更强的开头牵引力",
        ],
        "input_guide": "如果你已经知道本章核心卖点，最好写出来，例如悬念、冲突、谜团、反转或情绪爆点。",
        "output_format": ["章首吸引力判断", "3 条开场优化建议", "必要时给出替代开头"],
        "tips": [
            "不是所有章节都需要爆炸式开头，但至少要建立“读下去的理由”。",
            "适合和“章末悬念”一起搭配，形成首尾牵引。",
        ],
        "example_prompt": "检查这一章开头是否太慢，并给我一个更抓人的开篇方案。",
        "tags": ["开头", "章节", "抓钩"],
        "instruction_template": "请评估当前章首是否具备吸引力和阅读牵引力，并给出3条更强的开场优化建议。",
    },
    {
        "id": "chapter-ending-cliffhanger",
        "name": "章末悬念强化",
        "description": "检查章尾是否有足够的悬念、余波或情绪牵引，增强续读动力。",
        "overview": "适合连载和章节化长篇，帮助你判断章尾是否停在最值得下一章继续的节点。",
        "category": "结构",
        "author": "玄穹文枢",
        "version": "0.1.0",
        "source_url": None,
        "use_cases": [
            "章尾收得太平，读者没有继续点下一章的冲动",
            "高潮后收束过度，把余震也写没了",
            "想强化反转、悬念或情绪余波",
        ],
        "input_guide": "说明你想要的章尾效果，例如“强悬念”“情绪余波”“危险预告”或“信息反转”。",
        "output_format": ["章尾诊断", "3 条悬念强化建议", "必要时给出替代收尾"],
        "tips": [
            "不一定非要断在大反转，也可以断在即将爆发前的压缩点。",
            "如果章节本身偏静，可以强调信息差或情绪余温。",
        ],
        "example_prompt": "检查这一章结尾是否太平，并给出一个更能带动续读的收尾方案。",
        "tags": ["结尾", "悬念", "续读"],
        "instruction_template": "请评估章末悬念、余波和续读牵引是否足够，并给出3条更强的收尾优化建议。",
    },
    {
        "id": "motivation-consistency-checker",
        "name": "动机一致性检查",
        "description": "核对人物行为、选择与其既有目标、伤口和立场是否一致。",
        "overview": "适合人物做出关键选择后回头核查，避免“为了剧情需要而硬拐弯”的违和感。",
        "category": "角色",
        "author": "玄穹文枢",
        "version": "0.1.0",
        "source_url": None,
        "use_cases": [
            "角色突然改变立场，担心说服力不足",
            "剧情推进需要人物做高风险决定",
            "角色设定丰富，但行动逻辑容易飘",
        ],
        "input_guide": "指出你担心哪位角色在这一章“做了不太像他/她会做的事”，技能会重点检查动机链。",
        "output_format": ["一致性判断", "3 条补强建议", "必要时给出补桥段方式"],
        "tips": [
            "如果角色前史很重要，建议在输入里提醒技能参考旧伤、秘密或核心执念。",
            "适合在大转折前后使用。",
        ],
        "example_prompt": "检查男主这一章突然决定救仇人是否动机不足，并告诉我该怎么补桥。",
        "tags": ["角色", "动机", "一致性"],
        "instruction_template": "请检查角色行为与既有目标、伤口、立场是否一致，指出最容易出戏的地方，并给出3条补强建议。",
    },
    {
        "id": "emotion-arc-calibrator",
        "name": "情绪曲线校准",
        "description": "检查章节内部情绪推进是否顺滑，避免爆点失衡或情绪断裂。",
        "overview": "适合处理情绪戏、关系戏和高压章节，帮助你判断情绪起伏是否层层递进，而不是平铺或乱跳。",
        "category": "情绪",
        "author": "玄穹文枢",
        "version": "0.1.0",
        "source_url": None,
        "use_cases": [
            "情绪爆点来得太突然或太弱",
            "人物关系戏缺少递进层次",
            "多场景章节里情绪波动不连贯",
        ],
        "input_guide": "说明你想校准的是哪条情绪线，例如恐惧、愤怒、暧昧、哀伤或压迫感。",
        "output_format": ["情绪线判断", "3 条校准建议", "必要时给出段落调整方案"],
        "tips": [
            "如果这一章有多个情绪峰值，建议在输入里指出你想保留的主峰。",
            "适合跟“角色声音”或“对白潜台词”配合优化。",
        ],
        "example_prompt": "检查这一章师徒关系从冷战到和解的情绪递进是否自然，并给出调整建议。",
        "tags": ["情绪", "递进", "关系戏"],
        "instruction_template": "请检查章节情绪曲线是否自然递进，指出最突兀或最平的部分，并给出3条具体调整建议。",
    },
    {
        "id": "prose-clarity-polisher",
        "name": "语言清晰度润色",
        "description": "找出拗口、重复、信息拥堵的句段，提升可读性而不削弱风格。",
        "overview": "适合在定稿前快速找出句子层面的阻塞点，尤其对长句、信息密度高的段落很有效。",
        "category": "文风",
        "author": "玄穹文枢",
        "version": "0.1.0",
        "source_url": None,
        "use_cases": [
            "句子太绕，读起来发涩",
            "说明信息集中，读者容易漏看",
            "想保留风格但减少重复和拖泥带水",
        ],
        "input_guide": "可以直接说“帮我找这一章最拗口的 3 处”，也可以限定某一段做语言清晰化。",
        "output_format": ["清晰度判断", "3 条润色建议", "必要时给出更顺的替代句"],
        "tips": [
            "它不会默认把你的文风全洗平，更偏向保留信息和语气的前提下做减负。",
            "适合定稿前最后一轮整理。",
        ],
        "example_prompt": "找出这一章最拗口、最重复的 3 处表达，并给出更顺的替代写法。",
        "tags": ["润色", "清晰度", "可读性"],
        "instruction_template": "请找出文本里最影响可读性的表达问题，指出重复、拗口和信息拥堵处，并给出3条不削弱风格的润色建议。",
    },
]

EXTRA_SKILL_DEFINITIONS: list[dict[str, Any]] = [
    {"id": "foreshadowing-density-balancer", "name": "伏笔密度平衡器", "description": "检查伏笔投放密度是否失衡。", "category": "结构", "author": "玄穹文枢", "version": "0.1.0"},
    {"id": "pov-stability-checker", "name": "视角稳定性检查", "description": "检查视角是否漂移、串位或突然越界。", "category": "叙述", "author": "玄穹文枢", "version": "0.1.0"},
]

ALL_SKILL_DEFINITIONS = [*SKILL_DEFINITIONS, *EXTRA_SKILL_DEFINITIONS]
SKILL_DEFINITION_MAP = {item["id"]: item for item in ALL_SKILL_DEFINITIONS}

SKILL_TEXT_OVERRIDES: dict[str, dict[str, Any]] = {
    "scene-conflict-booster": {
        "name": "场景冲突强化",
        "description": "强化当前场景中的目标、阻力、代价与选择，让冲突更抓人。",
        "overview": "适合在章节已经写完，但场面张力不足时使用，帮助把核心冲突重新拉到台前。",
        "category": "情节",
        "use_cases": ["场景过平", "对话有信息但没压迫感", "想加强利益冲突或情绪冲突"],
        "input_guide": "写清这一场的目标、阻碍，以及你觉得不够强的地方。",
        "output_format": ["问题判断", "3 条强化建议", "必要时给出一小段改写示例"],
        "tips": ["尽量补一句你想加强的冲突类型。", "如果绑定了章节，会自动结合当前正文分析。"],
        "example_prompt": "检查这一章主角和掌柜谈判的冲突是否太平，并给出可直接改写进正文的建议。",
        "tags": ["场景", "冲突", "改写"],
    },
    "character-voice-polisher": {
        "name": "角色声音校准",
        "description": "检查对白是否贴合角色身份、关系和情绪状态。",
        "overview": "适合处理“所有人说话都像一个人”的问题，拉开不同角色的话语风格。",
        "category": "角色",
        "use_cases": ["角色辨识度低", "高压场面下对白太平", "想区分主角与配角的说话方式"],
        "input_guide": "指出你担心失真的角色，或直接指定要对比的两个角色。",
        "output_format": ["失真判断", "3 条替换建议", "必要时给出示例对白"],
        "tips": ["补充角色身份、年龄和关系，建议会更准。"],
        "example_prompt": "检查女主和军师在这一章里的对白是否说得太像同一种人。",
        "tags": ["角色", "对白", "语气"],
    },
    "clue-layout-checker": {
        "name": "线索布局检查",
        "description": "检查伏笔、误导和回收点是否清楚、稳定、可追踪。",
        "category": "推理",
        "tags": ["推理", "线索", "伏笔"],
    },
    "pacing-rhythm-tuner": {
        "name": "章节节奏调校",
        "description": "检查信息推进、场景切换和情绪波动，避免章节过慢或过赶。",
        "category": "节奏",
        "tags": ["节奏", "结构", "章节"],
    },
    "show-dont-tell-rewriter": {
        "name": "展示感改写器",
        "description": "把直说式叙述改成更有画面感、更能被读者感知的表达。",
        "category": "叙述",
        "tags": ["叙述", "改写", "画面感"],
    },
    "dialogue-subtext-enhancer": {
        "name": "对白潜台词增强",
        "description": "强化对白中的试探、遮掩、压迫和关系张力，让话里有话。",
        "category": "对白",
        "tags": ["对白", "潜台词", "张力"],
    },
    "chapter-hook-designer": {
        "name": "章首抓钩设计",
        "description": "检查开场是否足够抓人，帮助章节更快进入状态。",
        "category": "结构",
        "tags": ["开头", "抓钩", "章节"],
    },
    "chapter-ending-cliffhanger": {
        "name": "章末悬念强化",
        "description": "检查章节收尾是否具备悬念、余波或继续阅读牵引力。",
        "category": "结构",
        "tags": ["结尾", "悬念", "续读"],
    },
    "motivation-consistency-checker": {
        "name": "动机一致性检查",
        "description": "核对角色行为与既有目标、伤口、立场是否一致。",
        "category": "角色",
        "tags": ["动机", "角色", "一致性"],
    },
    "emotion-arc-calibrator": {
        "name": "情绪曲线校准",
        "description": "检查章节内部情绪推进是否自然，避免爆点失衡或情绪断裂。",
        "category": "情绪",
        "tags": ["情绪", "递进", "关系戏"],
    },
    "prose-clarity-polisher": {
        "name": "语言清晰度润色",
        "description": "找出拗口、重复和信息拥堵的句段，提升可读性但不洗掉风格。",
        "category": "文风",
        "tags": ["润色", "清晰度", "可读性"],
    },
    "foreshadowing-density-balancer": {
        "name": "伏笔密度平衡器",
        "description": "检查伏笔是否过密、过散或互相抢戏，帮助控制信息投放节奏。",
        "overview": "适合推理、悬疑、长线布局章节，避免读者被过多提示打断阅读。",
        "category": "结构",
        "use_cases": ["伏笔太多显得刻意", "信息点太少撑不起后续回收", "中段铺垫失衡"],
        "input_guide": "说明你想检查哪一段的伏笔投放密度，或指出你担心的关键提示。",
        "output_format": ["密度判断", "3 条调整建议", "必要时给出局部改写示例"],
        "tips": ["适合与线索布局检查一起使用。"],
        "example_prompt": "检查这一章前半段的伏笔是否过密，并给出更自然的调整方式。",
        "tags": ["伏笔", "密度", "节奏"],
    },
    "pov-stability-checker": {
        "name": "视角稳定性检查",
        "description": "检查叙述视角是否漂移、串位或突然跳出当前视角角色。",
        "overview": "适合多角色长篇和近距离视角章节，避免读者出戏。",
        "category": "叙述",
        "use_cases": ["视角忽近忽远", "突然知道不该知道的信息", "多角色章节易串视角"],
        "input_guide": "说明当前章节采用的视角方式，或指出你怀疑串位的段落。",
        "output_format": ["视角判断", "3 条修正建议", "必要时给出改写示例"],
        "tips": ["如果是第三人称限知，最好在输入里明确说明。"],
        "example_prompt": "检查这一章是否有视角漂移，尤其是男主和女主对话段落。",
        "tags": ["视角", "叙述", "稳定性"],
    },
}


class WritingSkillsService:
    """写作技能服务"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.novel_repo = NovelRepository(db)
        self.llm_service = LLMService(db)

    @staticmethod
    def _build_skill_payload(definition: dict[str, Any]) -> dict[str, Any]:
        override = SKILL_TEXT_OVERRIDES.get(definition["id"], {})
        merged = {**definition, **override}
        return {
            "id": merged["id"],
            "name": merged["name"],
            "description": merged["description"],
            "overview": merged.get("overview"),
            "category": merged.get("category"),
            "author": merged.get("author"),
            "version": merged.get("version", "0.1.0"),
            "source_url": merged.get("source_url"),
            "use_cases": list(merged.get("use_cases") or []),
            "input_guide": merged.get("input_guide"),
            "output_format": list(merged.get("output_format") or []),
            "tips": list(merged.get("tips") or []),
            "example_prompt": merged.get("example_prompt"),
            "tags": list(merged.get("tags") or []),
        }

    def get_skill_definition(self, skill_id: str) -> Optional[dict[str, Any]]:
        definition = SKILL_DEFINITION_MAP.get(skill_id)
        if not definition:
            return None
        return self._build_skill_payload(definition)

    async def get_installed_skills(self) -> list[WritingSkill]:
        result = await self.db.execute(
            select(WritingSkill).order_by(WritingSkill.enabled.desc(), WritingSkill.installed_at.desc())
        )
        return result.scalars().all()

    async def get_skill_detail(self, skill_id: str) -> Optional[WritingSkill]:
        result = await self.db.execute(select(WritingSkill).where(WritingSkill.id == skill_id))
        return result.scalar_one_or_none()

    async def fetch_skill_catalog(self) -> list[dict[str, Any]]:
        installed = {skill.id for skill in await self.get_installed_skills()}
        catalog: list[dict[str, Any]] = []
        for definition in ALL_SKILL_DEFINITIONS:
            payload = self._build_skill_payload(definition)
            payload["installed"] = payload["id"] in installed
            catalog.append(payload)
        return catalog

    def _validate_source_url(self, source_url: Optional[str]) -> Optional[str]:
        if not source_url:
            return None
        parsed = urlparse(source_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("技能来源地址无效")
        if "github.com" not in parsed.netloc.lower():
            raise ValueError("当前仅支持 GitHub 来源地址")
        return source_url

    async def install_skill(
        self,
        skill_id: str,
        name: str,
        description: Optional[str] = None,
        category: Optional[str] = None,
        version: str = "0.1.0",
        author: Optional[str] = None,
        source_url: Optional[str] = None,
    ) -> WritingSkill:
        source_url = self._validate_source_url(source_url)
        skill = await self.get_skill_detail(skill_id)
        if skill:
            skill.name = name
            skill.description = description
            skill.category = category
            skill.version = version
            skill.author = author
            skill.source_url = source_url
            skill.enabled = True
        else:
            skill = WritingSkill(
                id=skill_id,
                name=name,
                description=description,
                category=category,
                version=version,
                author=author,
                source_url=source_url,
                enabled=True,
            )
            self.db.add(skill)

        await self.db.commit()
        await self.db.refresh(skill)
        return skill

    async def uninstall_skill(self, skill_id: str) -> bool:
        skill = await self.get_skill_detail(skill_id)
        if not skill:
            return False
        await self.db.delete(skill)
        await self.db.commit()
        return True

    async def execute_skill(
        self,
        skill_id: str,
        prompt: str,
        project_id: Optional[str] = None,
        chapter_number: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> dict[str, Any]:
        skill = await self.get_skill_detail(skill_id)
        if not skill or not skill.enabled:
            raise ValueError("技能不存在或未启用")

        prompt = (prompt or "").strip()
        if not prompt:
            raise ValueError("请先输入技能执行内容")

        project_context = ""
        chapter_context = ""
        if project_id:
            project = await self.novel_repo.get_by_id(project_id)
            if not project:
                raise ValueError("项目不存在")
            project_context = (
                f"项目标题：{project.title}\n"
                f"一句话简介：{project.blueprint.one_sentence_summary if project.blueprint else ''}\n"
                f"世界设定：{project.blueprint.world_setting if project.blueprint else {}}\n"
            )
            if chapter_number is not None:
                chapter = next((item for item in project.chapters if item.chapter_number == chapter_number), None)
                if chapter:
                    selected_version = chapter.selected_version.content if chapter.selected_version else None
                    latest_version = chapter.versions[-1].content if chapter.versions else None
                    chapter_text = selected_version or latest_version or ""
                    chapter_context = (
                        f"章节号：第 {chapter_number} 章\n"
                        f"章节摘要：{chapter.real_summary or ''}\n"
                        f"章节正文：{chapter_text[:6000]}\n"
                    )

        skill_definition = SKILL_DEFINITION_MAP.get(skill_id)
        skill_instruction = (
            skill_definition.get("instruction_template")
            if skill_definition and skill_definition.get("instruction_template")
            else "请给出具体、可执行的写作改进建议。"
        )

        composed_prompt = (
            f"你是 玄穹文枢 的写作技能助手。\n"
            f"技能：{skill.name}\n"
            f"技能目标：{skill_instruction}\n\n"
            f"用户要求：{prompt}\n\n"
            f"{project_context}"
            f"{chapter_context}"
            "请直接输出：1）问题判断；2）3条具体修改建议；3）如有必要给出一小段示例改写。"
        )

        suggestion = await self.llm_service.generate(
            composed_prompt,
            system_prompt="你是一名严谨的小说编辑与写作教练。输出必须具体、可执行、贴合上下文。",
            temperature=0.5,
            user_id=user_id,
            response_format=None,
            max_tokens=1200,
        )

        result = {
            "summary": f"已执行技能：{skill.name}",
            "suggestion": suggestion,
            "mode": "llm",
        }

        execution = SkillExecution(
            skill_id=skill.id,
            project_id=project_id,
            chapter_number=chapter_number,
            prompt=prompt,
            result=result["suggestion"],
        )
        self.db.add(execution)
        await self.db.commit()
        await self.db.refresh(execution)

        return {
            "skill_id": skill.id,
            "skill_name": skill.name,
            "project_id": project_id,
            "chapter_number": chapter_number,
            "result": result,
            "executed_at": execution.executed_at.isoformat(),
        }
