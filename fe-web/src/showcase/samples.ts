/**
 * Public, manually authored teaching examples. The short prose was reviewed
 * from DemoManifest.java's source fixture, never exported from a running service.
 * Prepared answers and choice grading are deliberately part of this public bundle.
 */
export const SAMPLE_VERSION = '2026-09-v1' as const;

export type Section = {
  readonly id: string;
  readonly title: string;
  readonly paragraphs: readonly string[];
};

export type RecommendedQuestion = {
  readonly id: string;
  readonly question: string;
  readonly answer: string;
  readonly source: { readonly sectionId: string; readonly paragraphIndex: number };
};

export type QuizQuestion = {
  readonly id: string;
  readonly prompt: string;
  readonly choices: readonly { readonly id: string; readonly text: string }[];
  readonly correctChoiceId: string;
  readonly explanation: string;
};

export type Sample = {
  readonly id: string;
  readonly title: string;
  readonly description: string;
  readonly category: string;
  readonly sections: readonly Section[];
  readonly recommendations: readonly RecommendedQuestion[];
  readonly quiz: readonly QuizQuestion[];
};

export const samples: readonly Sample[] = [
  {
    id: 'water-journey',
    title: '물의 여행',
    description: '물이 모습을 바꾸고 다시 돌아오는 길을 함께 살펴봐요.',
    category: '생활 과학',
    sections: [
      {
        id: 'water-1', title: '얼음과 물',
        paragraphs: [
          '물은 주변의 온도에 따라 모습이 달라집니다.',
          '물이 충분히 차가워지면 단단한 얼음이 됩니다. 얼음을 따뜻한 곳에 두면 다시 물이 됩니다.',
        ],
      },
      {
        id: 'water-2', title: '하늘로 올라가는 물',
        paragraphs: [
          '젖은 수건을 널어 두면 조금씩 마릅니다. 수건 속 물이 눈에 보이지 않는 수증기가 되어 공기 중으로 나가기 때문입니다.',
          '액체인 물이 기체로 바뀌는 일을 증발이라고 합니다.',
        ],
      },
      {
        id: 'water-3', title: '다시 땅으로 돌아오는 물',
        paragraphs: [
          '하늘의 수증기가 차가워지면 작은 물방울이 생깁니다. 작은 물방울이 모여 구름을 이룹니다.',
          '물방울이 커지고 무거워지면 비가 되어 내려옵니다. 물은 이렇게 여러 모습을 바꾸며 여행합니다.',
        ],
      },
    ],
    recommendations: [
      {
        id: 'water-ice', question: '물이 충분히 차가워지면 무엇이 되나요?',
        answer: '물이 충분히 차가워지면 단단한 얼음이 됩니다. 얼음을 따뜻한 곳에 두면 다시 물로 바뀝니다.',
        source: { sectionId: 'water-1', paragraphIndex: 1 },
      },
      {
        id: 'water-evaporation', question: '젖은 수건이 마르는 까닭은 무엇인가요?',
        answer: '수건 속 물이 수증기가 되어 공기 중으로 나가기 때문입니다. 액체인 물이 기체로 바뀌는 것을 증발이라고 해요.',
        source: { sectionId: 'water-2', paragraphIndex: 0 },
      },
    ],
    quiz: [
      {
        id: 'water-quiz-ice', prompt: '물이 충분히 차가워지면 무엇이 되나요?',
        choices: [{ id: 'ice', text: '얼음' }, { id: 'cloud', text: '구름' }, { id: 'sand', text: '모래' }],
        correctChoiceId: 'ice', explanation: '본문에서는 물이 충분히 차가워지면 단단한 얼음이 된다고 설명합니다.',
      },
      {
        id: 'water-quiz-vapor', prompt: '액체인 물이 기체로 바뀌는 일을 무엇이라고 하나요?',
        choices: [{ id: 'freeze', text: '얼기' }, { id: 'evaporate', text: '증발' }, { id: 'melt', text: '녹기' }],
        correctChoiceId: 'evaporate', explanation: '물에서 수증기로 모습이 바뀌는 일은 증발입니다.',
      },
    ],
  },
  {
    id: 'recycling-day',
    title: '생활 속 분리배출',
    description: '사용한 물건을 살펴보고 알맞게 나누어 버려요.',
    category: '생활 습관',
    sections: [
      {
        id: 'recycling-1', title: '먼저 비우고 헹구기',
        paragraphs: [
          '분리배출은 사용한 물건을 재질에 따라 나누어 버리는 일입니다.',
          '음료가 담겼던 용기는 내용물을 먼저 비웁니다. 음식물이 묻었다면 가볍게 헹굽니다. 깨끗하게 나누어 모으면 다시 쓸 수 있는 자원이 됩니다.',
        ],
      },
      {
        id: 'recycling-2', title: '종이와 용기 살펴보기',
        paragraphs: [
          '깨끗한 종이는 젖지 않게 모읍니다. 상자에 붙은 테이프처럼 다른 재질은 떼어 냅니다.',
          '용기에도 서로 다른 재질의 뚜껑이나 라벨이 붙어 있을 수 있습니다. 분리할 수 있는 부분은 나누어 모읍니다.',
        ],
      },
      {
        id: 'recycling-3', title: '안내를 확인하기',
        paragraphs: [
          '모든 물건을 같은 곳에 버리지는 않습니다. 사는 곳마다 분리배출 장소와 날짜가 다를 수 있습니다.',
          '헷갈릴 때는 거주 지역의 분리배출 안내를 확인합니다. 무조건 재활용함에 넣기보다 안내에 맞게 버리는 것이 중요합니다.',
        ],
      },
    ],
    recommendations: [
      {
        id: 'recycling-empty', question: '음료 용기를 분리배출하기 전에 무엇을 하나요?',
        answer: '내용물을 먼저 비우고, 음식물이 묻었다면 가볍게 헹굽니다. 깨끗하게 나누어 모으면 다시 쓸 수 있는 자원이 됩니다.',
        source: { sectionId: 'recycling-1', paragraphIndex: 1 },
      },
      {
        id: 'recycling-guide', question: '분리배출 방법이 헷갈리면 어떻게 하나요?',
        answer: '거주 지역의 분리배출 안내를 확인합니다. 장소와 날짜가 다를 수 있으니 안내에 맞게 버려요.',
        source: { sectionId: 'recycling-3', paragraphIndex: 1 },
      },
    ],
    quiz: [
      {
        id: 'recycling-quiz-empty', prompt: '음료 용기를 분리배출하기 전에 내용물을 어떻게 하나요?',
        choices: [{ id: 'empty', text: '먼저 비워요' }, { id: 'fill', text: '가득 채워요' }, { id: 'mix', text: '다른 쓰레기와 섞어요' }],
        correctChoiceId: 'empty', explanation: '내용물을 비우고 음식물이 묻었다면 가볍게 헹굽니다.',
      },
      {
        id: 'recycling-quiz-guide', prompt: '분리배출 방법이 헷갈릴 때 어떻게 하나요?',
        choices: [{ id: 'local-guide', text: '거주 지역의 안내를 확인해요' }, { id: 'always-recycle', text: '무조건 재활용함에 넣어요' }, { id: 'guess', text: '짐작해서 버려요' }],
        correctChoiceId: 'local-guide', explanation: '사는 곳마다 안내가 다를 수 있어 거주 지역의 분리배출 안내를 확인합니다.',
      },
    ],
  },
];

export function findSample(id: string | undefined): Sample | undefined {
  return samples.find((sample) => sample.id === id);
}
