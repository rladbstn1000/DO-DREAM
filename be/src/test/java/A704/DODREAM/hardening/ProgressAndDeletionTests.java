package A704.DODREAM.hardening;

import A704.DODREAM.authorization.AuthorizationPolicy;
import A704.DODREAM.material.entity.Material;
import A704.DODREAM.material.repository.MaterialRepository;
import A704.DODREAM.material.service.PublishService;
import A704.DODREAM.progress.entity.StudentMaterialProgress;
import A704.DODREAM.report.service.ProgressReportService;
import A704.DODREAM.report.repository.StudentMaterialProgressRepository;
import A704.DODREAM.material.repository.MaterialShareRepository;
import A704.DODREAM.user.repository.UserRepository;
import org.junit.jupiter.api.Test;
import software.amazon.awssdk.services.s3.S3Client;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class ProgressAndDeletionTests {
    @Test void deletingMaterialDoesNotDeleteRemoteHistoryEvenWhenDatabaseSaveFails() {
        var policy=mock(AuthorizationPolicy.class); var materials=mock(MaterialRepository.class); var storage=mock(S3Client.class);
        var service=new PublishService(policy,null,null,null,materials,null,storage,null,null,null,null);
        var material=Material.builder().id(11L).build();
        when(materials.findByIdAndTeacherIdAndDeletedAtIsNull(11L,1L)).thenReturn(java.util.Optional.of(material));
        doThrow(new IllegalStateException("synthetic database failure")).when(materials).save(material);
        assertThrows(IllegalStateException.class,()->service.deleteMaterial(1L,11L));
        verify(policy).owned(1L,11L); verifyNoInteractions(storage);
        assertTrue(material.isDeleted()); // Managed entity is rolled back by the surrounding real transaction.
    }
    @Test void changedDocumentLengthRecomputesCompletionWithoutOutOfRangeProgress() {
        var progress=StudentMaterialProgress.builder().currentPage(2).totalPages(3).build();
        progress.updateProgress(3); assertNotNull(progress.getCompletedAt());
        progress.updateTotalPages(5); assertNull(progress.getCompletedAt()); assertEquals(3,progress.getCurrentPage());
        progress.updateProgress(1); assertEquals(3,progress.getCurrentPage());
        progress.updateTotalPages(2); assertEquals(2,progress.getCurrentPage()); assertNotNull(progress.getCompletedAt());
        assertThrows(IllegalArgumentException.class,()->progress.updateProgress(-1));
        assertThrows(IllegalArgumentException.class,()->progress.updateProgress(3));
        assertThrows(IllegalArgumentException.class,()->progress.updateTotalPages(0));
    }
    @Test void normalUpdateCapsAnExistingLegacyOutOfRangeValue() {
        var progress=StudentMaterialProgress.builder().currentPage(5).totalPages(3).build();
        progress.updateProgress(1);
        assertEquals(3,progress.getCurrentPage()); assertNotNull(progress.getCompletedAt());
    }
    @Test void omittedTotalPreservesPreviouslyKnownDocumentLength() {
        var policy=mock(AuthorizationPolicy.class); var progressRepository=mock(StudentMaterialProgressRepository.class);
        var materials=mock(MaterialRepository.class); var shares=mock(MaterialShareRepository.class);
        var users=mock(UserRepository.class); var storage=mock(S3Client.class);
        var user=A704.DODREAM.user.entity.User.create("synthetic",A704.DODREAM.user.entity.Role.STUDENT);
        var material=Material.builder().id(2L).build();
        var progress=StudentMaterialProgress.builder().student(user).material(material).currentPage(5).totalPages(10).build();
        when(users.findById(1L)).thenReturn(java.util.Optional.of(user));
        when(shares.findByStudentIdAndMaterialId(1L,2L)).thenReturn(java.util.Optional.of(
            A704.DODREAM.material.entity.MaterialShare.builder().material(material).build()));
        when(progressRepository.findByStudentIdAndMaterialId(1L,2L)).thenReturn(java.util.Optional.of(progress));
        when(progressRepository.save(progress)).thenReturn(progress);
        var service=new ProgressReportService(policy,progressRepository,materials,shares,users,storage,new com.fasterxml.jackson.databind.ObjectMapper());
        var response=service.updateProgress(1L,2L,2,null);
        assertEquals(10,response.getTotalPages()); assertEquals(5,response.getCurrentPage());
        assertEquals(50,response.getProgressPercentage()); assertNull(response.getCompletedAt());
    }
    @Test void invalidProgressNeverReadsOrWritesProgressRows() {
        var policy=mock(AuthorizationPolicy.class); var progress=mock(StudentMaterialProgressRepository.class);
        var materials=mock(MaterialRepository.class); var shares=mock(MaterialShareRepository.class);
        var users=mock(UserRepository.class); var storage=mock(S3Client.class);
        var service=new ProgressReportService(policy,progress,materials,shares,users,storage,new com.fasterxml.jackson.databind.ObjectMapper());
        Integer[][] invalid={{null,3},{-1,3},{4,3},{1,0},{1,-1},{100001,100001}};
        for(var range:invalid) assertThrows(A704.DODREAM.authorization.AuthorizationFailure.class,
            ()->service.updateProgress(1L,2L,range[0],range[1]));
        verifyNoInteractions(progress,materials,shares,users,storage);
    }
}
