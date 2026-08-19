import { computed, ref } from 'vue'

/**
 * 像素吉祥物：12×12 网格、4 帧逐帧动画。
 *
 * 像素编码（每帧 12 行字符串，每行 12 个字符）：
 *   `.` 透明        `1` 主色（用户自定义）   `2` 主色暗部（轮廓/阴影）
 *   `4` 暖色（喙/爪/腮红）                   `5` 近黑（眼睛/鼻子）
 *   `6` 纯白（吻部/胸腹/眼白）
 *
 * 一只动物 = 9 行「身体」（固定，负责辨识度）+ 3 行「下肢」（按步态逐帧变化）。
 * 这样 10 种动物可以自由搭配 6 种推进姿态，也便于随机切换。
 */
export type PixelMascotId =
  | 'cat'
  | 'fox'
  | 'rabbit'
  | 'panda'
  | 'frog'
  | 'penguin'
  | 'hamster'
  | 'otter'
  | 'duck'
  | 'bear'

/** 推进姿态：走路 / 跑动 / 跳跃 / 游泳 / 摇摆 / 蠕动 */
export type MascotGaitId = 'walk' | 'run' | 'hop' | 'swim' | 'waddle' | 'wriggle'

/** 'auto' 表示每次开始推进时随机挑一种姿态 */
export type MascotGaitMode = MascotGaitId | 'auto'

export interface MascotGait {
  id: MascotGaitId
  name: string
  nameEn: string
  /** 单帧停留时长（毫秒），越小动作越快 */
  frameDuration: number
  /** 4 帧 × 3 行下肢像素 */
  legs: string[][]
}

export interface PixelMascotOption {
  id: PixelMascotId
  name: string
  nameEn: string
  /** 默认姿态，用户未指定时使用 */
  defaultGait: MascotGaitId
  /** 9 行身体像素 */
  body: string[]
}

/** 6 种推进姿态的下肢帧库 */
export const MASCOT_GAITS: MascotGait[] = [
  {
    id: 'walk',
    name: '走路',
    nameEn: 'Walk',
    frameDuration: 190,
    legs: [
      ['...111111...', '...1...1....', '..44...44...'],
      ['...111111...', '....1.1.....', '...44.44....'],
      ['...111111...', '...1....1...', '..44....44..'],
      ['...111111...', '....1.1.....', '...44.44....'],
    ],
  },
  {
    id: 'run',
    name: '跑动',
    nameEn: 'Run',
    frameDuration: 110,
    legs: [
      ['...111111...', '..1.....1...', '.44......44.'],
      ['...111111...', '....11.1....', '...4..44....'],
      ['...111111...', '...1.....1..', '..44......44'],
      ['...111111...', '....1.11....', '....44.4....'],
    ],
  },
  {
    id: 'hop',
    name: '跳跃',
    nameEn: 'Hop',
    frameDuration: 170,
    legs: [
      ['...111111...', '...111111...', '..44....44..'],
      ['...111111...', '....1111....', '...44..44...'],
      ['...111111...', '....1..1....', '..44....44..'],
      ['...111111...', '....1111....', '...44..44...'],
    ],
  },
  {
    id: 'swim',
    name: '游泳',
    nameEn: 'Swim',
    frameDuration: 210,
    legs: [
      ['...111111...', '..44....44..', '.2..2..2..2.'],
      ['...111111...', '.44......44.', '..2..2..2..2'],
      ['...111111...', '..44....44..', '2..2..2..2..'],
      ['...111111...', '.44......44.', '.2..2..2..2.'],
    ],
  },
  {
    id: 'waddle',
    name: '摇摆',
    nameEn: 'Waddle',
    frameDuration: 230,
    legs: [
      ['...111111...', '...11..11...', '..444..444..'],
      ['...111111...', '..11....11..', '.444....444.'],
      ['...111111...', '...11..11...', '..444..444..'],
      ['...111111...', '....1111....', '...44..44...'],
    ],
  },
  {
    id: 'wriggle',
    name: '蠕动',
    nameEn: 'Wriggle',
    frameDuration: 260,
    legs: [
      ['...111111...', '..11111111..', '...222222...'],
      ['..1111111...', '...111111...', '....2222....'],
      ['...111111...', '..11111111..', '...222222...'],
      ['...1111111..', '...111111...', '....2222....'],
    ],
  },
]

/** 10 种动物身体：靠耳朵形状、吻部、眼睛做区分，缩到 22px 也能认出来 */
export const PIXEL_MASCOTS: PixelMascotOption[] = [
  {
    id: 'cat',
    name: '小猫',
    nameEn: 'Cat',
    defaultGait: 'walk',
    // 尖耳 + 胡须 + 小三角鼻
    body: [
      '..2......2..',
      '.21......12.',
      '.211....112.',
      '.1111111111.',
      '.1511111151.',
      '.1111441111.',
      '2.11111111.2',
      '..21111112..',
      '...111111...',
    ],
  },
  {
    id: 'fox',
    name: '小狐狸',
    nameEn: 'Fox',
    defaultGait: 'run',
    // 外扩大尖耳 + 白吻
    body: [
      '.2........2.',
      '.21......12.',
      '.211....112.',
      '.1111111111.',
      '.1511111151.',
      '.1111111111.',
      '2.16666661.2',
      '..26655662..',
      '...166661...',
    ],
  },
  {
    id: 'rabbit',
    name: '小兔',
    nameEn: 'Rabbit',
    defaultGait: 'hop',
    // 长直耳 + 三瓣嘴
    body: [
      '...21..12...',
      '...21..12...',
      '..21111112..',
      '.1111111111.',
      '.1511111151.',
      '.1111441111.',
      '2.11666611.2',
      '..21111112..',
      '...111111...',
    ],
  },
  {
    id: 'panda',
    name: '熊猫',
    nameEn: 'Panda',
    defaultGait: 'waddle',
    // 圆黑耳 + 大黑眼圈
    body: [
      '.22......22.',
      '.22......22.',
      '.2111111112.',
      '.1111111111.',
      '.1551111551.',
      '.1551111551.',
      '2.11155111.2',
      '..21111112..',
      '...166661...',
    ],
  },
  {
    id: 'frog',
    name: '青蛙',
    nameEn: 'Frog',
    defaultGait: 'hop',
    // 头顶凸眼 + 宽嘴
    body: [
      '..66....66..',
      '..65....56..',
      '.2111111112.',
      '.1111111111.',
      '.1111111111.',
      '.1555555551.',
      '.2111111112.',
      '..21111112..',
      '...111111...',
    ],
  },
  {
    id: 'penguin',
    name: '企鹅',
    nameEn: 'Penguin',
    defaultGait: 'waddle',
    // 暗色头罩 + 白胸 + 橙喙
    body: [
      '....2222....',
      '...222222...',
      '..22222222..',
      '..26222262..',
      '..22244222..',
      '.2266666622.',
      '.2166666612.',
      '..16666661..',
      '...166661...',
    ],
  },
  {
    id: 'hamster',
    name: '仓鼠',
    nameEn: 'Hamster',
    defaultGait: 'wriggle',
    // 小圆耳 + 鼓颊 + 门牙
    body: [
      '..22....22..',
      '.2111..1112.',
      '.1111111111.',
      '.1511111151.',
      '.1111441111.',
      '2.11666611.2',
      '.2116666112.',
      '..21111112..',
      '...111111...',
    ],
  },
  {
    id: 'otter',
    name: '水獭',
    nameEn: 'Otter',
    defaultGait: 'swim',
    // 扁头小耳 + 宽白吻
    body: [
      '.2........2.',
      '..2......2..',
      '.2111111112.',
      '.1511111151.',
      '.1111441111.',
      '.1116666111.',
      '2.11111111.2',
      '..21111112..',
      '...111111...',
    ],
  },
  {
    id: 'duck',
    name: '小鸭',
    nameEn: 'Duck',
    defaultGait: 'waddle',
    // 无耳圆头 + 宽扁橙喙
    body: [
      '....1111....',
      '...111111...',
      '..15111151..',
      '.1111111111.',
      '.1111111111.',
      '..11444411..',
      '..21444412..',
      '...211112...',
      '...111111...',
    ],
  },
  {
    id: 'bear',
    name: '小熊',
    nameEn: 'Bear',
    defaultGait: 'walk',
    // 大圆耳 + 白吻 + 黑鼻
    body: [
      '.22......22.',
      '.2211..1122.',
      '.1111111111.',
      '.1511111151.',
      '.1111111111.',
      '2.16666661.2',
      '..16655661..',
      '..21111112..',
      '...111111...',
    ],
  },
]

/** 颜色预设：与设计令牌同色系，避免随手挑出刺眼配色 */
export const MASCOT_COLOR_PRESETS = [
  '#4f46e5',
  '#0284c7',
  '#16a34a',
  '#d97706',
  '#dc2626',
  '#db2777',
  '#7c3aed',
  '#78716c',
]

export const MASCOT_GRID = 12
export const MASCOT_FRAME_COUNT = 4
const DEFAULT_COLOR = '#4f46e5'

const findMascot = (id: PixelMascotId | string | null): PixelMascotOption =>
  PIXEL_MASCOTS.find((item) => item.id === id) || PIXEL_MASCOTS[0]

const findGait = (id: MascotGaitId | string | null): MascotGait =>
  MASCOT_GAITS.find((item) => item.id === id) || MASCOT_GAITS[0]

/**
 * 合成 4 帧完整像素：身体 9 行 + 当前步态的 3 行下肢。
 * 返回值一定是 4 × 12 × 12 的合法数据，组件可以直接遍历。
 */
export function buildMascotFrames(
  mascotId: PixelMascotId | string,
  gaitId: MascotGaitId | string,
): string[][] {
  const body = findMascot(mascotId).body
  const legs = findGait(gaitId).legs
  return legs.map((legRows) => [...body, ...legRows])
}

const STORAGE_KEY = 'xuanqiong_wenshu_pixel_mascot'
const COLOR_KEY = 'xuanqiong_wenshu_pixel_mascot_color'
const GAIT_KEY = 'xuanqiong_wenshu_pixel_mascot_gait'

const readStorage = (key: string): string | null => {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

const writeStorage = (key: string, value: string) => {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* 隐私模式下写入失败不影响功能 */
  }
}

const mascotState = ref<PixelMascotId>(findMascot(readStorage(STORAGE_KEY)).id)
const colorState = ref(
  /^#[0-9a-f]{6}$/i.test(readStorage(COLOR_KEY) || '') ? (readStorage(COLOR_KEY) as string) : DEFAULT_COLOR,
)
const storedGait = readStorage(GAIT_KEY)
const gaitModeState = ref<MascotGaitMode>(
  storedGait === 'auto' || MASCOT_GAITS.some((item) => item.id === storedGait)
    ? (storedGait as MascotGaitMode)
    : 'auto',
)
/** auto 模式下当前随机命中的姿态；固定模式下不使用 */
const rolledGaitState = ref<MascotGaitId>(
  MASCOT_GAITS[Math.floor(Math.random() * MASCOT_GAITS.length)].id,
)
/**
 * 同屏可能有多个进度条（章节内嵌 + 悬浮卡片）共用这份全局姿态。
 * 用引用计数保证：一轮推进只在「第一个进度条开始」时随机换一次姿态，
 * 同屏所有吉祥物动作一致；全部结束后下一轮才会再换。
 */
const activeRunnerCount = ref(0)

export function usePixelMascot() {
  const mascot = computed(() => findMascot(mascotState.value))

  /** 实际生效的姿态 id：auto 时取随机结果，否则取用户固定选择 */
  const gaitId = computed<MascotGaitId>(() =>
    gaitModeState.value === 'auto' ? rolledGaitState.value : gaitModeState.value,
  )
  const gait = computed(() => findGait(gaitId.value))
  const frames = computed(() => buildMascotFrames(mascotState.value, gaitId.value))

  function setMascot(id: PixelMascotId) {
    mascotState.value = findMascot(id).id
    writeStorage(STORAGE_KEY, mascotState.value)
  }

  function setColor(color: string) {
    if (!/^#[0-9a-f]{6}$/i.test(color)) return
    colorState.value = color
    writeStorage(COLOR_KEY, color)
  }

  /** 传 'auto' 表示每轮推进随机换姿态 */
  function setGait(mode: MascotGaitMode) {
    const valid = mode === 'auto' || MASCOT_GAITS.some((item) => item.id === mode)
    gaitModeState.value = valid ? mode : 'auto'
    writeStorage(GAIT_KEY, gaitModeState.value)
    if (gaitModeState.value === 'auto') shuffleGait()
  }

  /** 重新随机一种姿态（auto 模式下每次开始生成时调用） */
  function shuffleGait() {
    const pool = MASCOT_GAITS.filter((item) => item.id !== rolledGaitState.value)
    const next = pool[Math.floor(Math.random() * pool.length)] || MASCOT_GAITS[0]
    rolledGaitState.value = next.id
    return next.id
  }

  /**
   * 进度条开始推进时调用：本轮第一个调用者会在 auto 模式下换一种姿态。
   * 返回本轮实际生效的姿态 id。
   */
  function beginRun() {
    const isFirstRunner = activeRunnerCount.value === 0
    activeRunnerCount.value += 1
    if (isFirstRunner && gaitModeState.value === 'auto') shuffleGait()
    return gaitId.value
  }

  /** 进度条停止推进（完成/失败/卸载）时调用，与 beginRun 成对 */
  function endRun() {
    activeRunnerCount.value = Math.max(0, activeRunnerCount.value - 1)
  }

  return {
    mascot,
    mascotId: mascotState,
    color: colorState,
    gait,
    gaitId,
    gaitMode: gaitModeState,
    frames,
    isRunning: computed(() => activeRunnerCount.value > 0),
    setMascot,
    setColor,
    setGait,
    shuffleGait,
    beginRun,
    endRun,
  }
}
