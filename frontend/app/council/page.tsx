import Sidebar from '@/components/Sidebar'
import Header from '@/components/Header'
import CouncilBoard from '@/components/council/CouncilBoard'

export default function CouncilPage() {
  return (
    <div className="flex h-screen bg-[#020617] text-[#f8fafc] overflow-hidden">
      <Sidebar />
      <div className="flex flex-1 flex-col min-w-0 lg:ml-[240px]">
        <Header />
        <main className="flex-1 overflow-y-auto">
          <div className="px-6 pt-6 pb-6">
            <CouncilBoard />
          </div>
        </main>
      </div>
    </div>
  )
}
