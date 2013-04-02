# -*- coding: utf-8 -*-

from mpi4py import MPI

from pyfr.backends.base import ComputeKernel, MPIKernel
from pyfr.backends.c.provider import CKernelProvider
from pyfr.backends.c.types import CMPIMatrix, CMPIView
from pyfr.nputil import npdtype_to_ctype


class CPackingKernels(CKernelProvider):
    def _packmodopts(self, mpiview):
        return dict(dtype=npdtype_to_ctype(mpiview.mpimat.dtype),
                    vlen=mpiview.view.vlen)

    def _packunpack_mpimat(self, op, mpimat):
        # MPI matrices are already packed, so this is a no-op
        class PackUnpackKernel(ComputeKernel):
            def run(self):
                pass

        return PackUnpackKernel()

    def _packunpack_mpiview(self, op, mpiview):
        # An MPI view is simply a regular view plus an MPI matrix
        v, m = mpiview.view, mpiview.mpimat

        fn = self._get_function('pack', op + '_view', None, 'NNPPPNNN',
                                self._packmodopts(mpiview))

        return self._basic_kernel(fn, v.nrow, v.ncol, v.mapping, v.strides, m,
                                  v.mapping.leaddim, v.strides.leaddim,
                                  m.leaddim)

    def _packunpack(self, op, mv):
        if isinstance(mv, CMPIMatrix):
            return self._packunpack_mpimat(op, mv)
        elif isinstance(mv, CMPIView):
            return self._packunpack_mpiview(op, mv)
        else:
            raise TypeError('Can only pack MPI views and MPI matrices')

    def _sendrecv(self, mv, mpipreqfn, pid, tag):
        # If we are an MPI view then extract the MPI matrix
        mpimat = mv.mpimat if isinstance(mv, CMPIView) else mv

        # Create a persistent MPI request to send/recv the pack
        preq = mpipreqfn(mpimat.data, pid, tag)

        class SendRecvPackKernel(MPIKernel):
            def run(self, reqlist):
                # Start the request and append us to the list of requests
                preq.Start()
                reqlist.append(preq)

        return SendRecvPackKernel()

    def pack(self, mv):
        return self._packunpack('pack', mv)

    def send_pack(self, mv, pid, tag):
        return self._sendrecv(mv, MPI.COMM_WORLD.Send_init, pid, tag)

    def recv_pack(self, mv, pid, tag):
        return self._sendrecv(mv, MPI.COMM_WORLD.Recv_init, pid, tag)

    def unpack(self, mv):
        return self._packunpack('unpack', mv)
