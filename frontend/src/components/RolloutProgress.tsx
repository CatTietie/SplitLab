import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Steps, Button, Space, Statistic, Modal, Typography, message } from 'antd'
import { ThunderboltOutlined, RollbackOutlined } from '@ant-design/icons'
import { experimentApi, type Experiment } from '../api'

const { Text } = Typography

interface RolloutProgressProps {
  experiment: Experiment
}

function RolloutProgress({ experiment }: RolloutProgressProps) {
  const queryClient = useQueryClient()
  const [confirmVisible, setConfirmVisible] = useState(false)

  const steps = experiment.rollout_steps || []
  const currentIndex = experiment.current_step_index ?? 0
  const currentPct = steps[currentIndex]?.traffic_percentage ?? 0

  const advanceMutation = useMutation({
    mutationFn: (confirmed: boolean) => experimentApi.advanceRollout(experiment.id, confirmed),
    onSuccess: () => {
      message.success('已推进到下一步')
      queryClient.invalidateQueries({ queryKey: ['experiment', experiment.id] })
    },
    onError: (err: any) => {
      if (err?.response?.status === 409) {
        setConfirmVisible(true)
      } else {
        message.error(err?.response?.data?.detail || '推进失败')
      }
    },
  })

  const rollbackMutation = useMutation({
    mutationFn: () => experimentApi.rollbackRollout(experiment.id),
    onSuccess: () => {
      message.success('已回退到上一步')
      queryClient.invalidateQueries({ queryKey: ['experiment', experiment.id] })
    },
    onError: (err: any) => {
      message.error(err?.response?.data?.detail || '回退失败')
    },
  })

  const isAtLastStep = currentIndex >= steps.length - 1
  const isAtFirstStep = currentIndex <= 0

  return (
    <div style={{ marginTop: 16, padding: 16, background: '#fafafa', borderRadius: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Text strong style={{ fontSize: 16 }}>灰度发布进度</Text>
        <Statistic
          title="当前 Treatment 流量"
          value={currentPct}
          suffix="%"
          valueStyle={{ color: '#1890ff', fontSize: 28 }}
        />
      </div>

      <Steps
        current={currentIndex}
        size="small"
        items={steps.map((step, idx) => ({
          title: `${step.traffic_percentage}%`,
          description: step.hold_seconds > 0 ? `停留 ${Math.round(step.hold_seconds / 60)} 分钟` : '手动控制',
          status: idx < currentIndex ? 'finish' : idx === currentIndex ? 'process' : 'wait',
        }))}
      />

      <Space style={{ marginTop: 16 }}>
        <Button
          type="primary"
          icon={<ThunderboltOutlined />}
          onClick={() => advanceMutation.mutate(false)}
          disabled={isAtLastStep}
          loading={advanceMutation.isPending}
        >
          推进到下一步
        </Button>
        <Button
          icon={<RollbackOutlined />}
          onClick={() => rollbackMutation.mutate()}
          disabled={isAtFirstStep}
          loading={rollbackMutation.isPending}
        >
          回退到上一步
        </Button>
      </Space>

      <Modal
        title="确认推进"
        open={confirmVisible}
        onOk={() => {
          setConfirmVisible(false)
          advanceMutation.mutate(true)
        }}
        onCancel={() => setConfirmVisible(false)}
        okText="确认推进"
        cancelText="取消"
      >
        <p>此前已发生回退，护栏指标可能仍有异常。确认要继续推进到下一步吗？</p>
      </Modal>
    </div>
  )
}

export default RolloutProgress
